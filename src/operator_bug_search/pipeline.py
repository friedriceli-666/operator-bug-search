from __future__ import annotations

import json
import re
import zlib
from datetime import datetime, timezone
from typing import Any

from .config import SearchConfig
from .github_client import GitHubApiError, GitHubClient
from .models import Finding
from .query_builder import SearchQuery, build_queries
from .storage import Storage

CODE_BLOCK_RE = re.compile(r"```(?:[\w.+-]+)?\n(.*?)```", re.DOTALL)


def _contains_repro_code(text: str) -> bool:
    if not text:
        return False
    if CODE_BLOCK_RE.search(text):
        return True
    hints = ["import torch", "cuda", "assert", "repro", "python", "tensor"]
    lower = text.lower()
    return any(hint in lower for hint in hints)


def _extract_code_snippets(text: str) -> list[str]:
    return [snippet.strip()[:4000] for snippet in CODE_BLOCK_RE.findall(text or "")]


def _find_matches(text: str, candidates: list[str]) -> list[str]:
    lowered = text.lower()
    return [candidate for candidate in candidates if candidate.lower() in lowered]


def _normalize_issue_item(
    item: dict[str, Any],
    query: SearchQuery,
    config: SearchConfig,
    comments: list[str],
) -> Finding:
    body = item.get("body") or ""
    merged_text = "\n".join([item.get("title") or "", body, *comments])
    source_type = "pull_request" if "pull_request" in item else "issue"
    return Finding(
        source_type=source_type,
        github_id=item["id"],
        html_url=item["html_url"],
        api_url=item["url"],
        repo_full_name=item["repository_url"].split("/repos/")[-1],
        title=item.get("title") or "",
        body=body,
        state=item.get("state") or "",
        labels=[label["name"] for label in item.get("labels", [])],
        matched_gpu_models=_find_matches(merged_text, config.gpu_models),
        matched_bug_keywords=_find_matches(merged_text, config.bug_keywords),
        suspected_stack=_find_matches(merged_text, config.stack_keywords),
        has_repro_code=_contains_repro_code(merged_text),
        code_snippets=_extract_code_snippets(merged_text),
        comments=comments,
        query=query.text,
        collected_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "score": item.get("score"),
            "comments_count": item.get("comments"),
        },
    )


def _normalize_code_item(
    item: dict[str, Any],
    query: SearchQuery,
    config: SearchConfig,
    fetched_content: str = "",
) -> Finding:
    repo_full_name = item["repository"]["full_name"]
    path = item.get("path") or ""
    merged_text = "\n".join([item.get("name") or "", path, fetched_content])
    return Finding(
        source_type="code",
        github_id=zlib.crc32(item["html_url"].encode("utf-8")),
        html_url=item["html_url"],
        api_url=item["url"],
        repo_full_name=repo_full_name,
        title=path,
        body=fetched_content,
        state="",
        labels=[],
        matched_gpu_models=_find_matches(merged_text, config.gpu_models),
        matched_bug_keywords=_find_matches(merged_text + "\n" + query.text, config.bug_keywords),
        suspected_stack=_find_matches(merged_text + "\n" + query.text, config.stack_keywords),
        has_repro_code=_contains_repro_code(fetched_content or path),
        code_snippets=_extract_code_snippets(fetched_content) or ([fetched_content[:4000]] if fetched_content else []),
        comments=[],
        query=query.text,
        collected_at=datetime.now(timezone.utc).isoformat(),
        metadata={
            "path": path,
            "sha": item.get("sha"),
        },
    )


class GitHubCollectionPipeline:
    def __init__(self, client: GitHubClient, storage: Storage, config: SearchConfig) -> None:
        self.client = client
        self.storage = storage
        self.config = config

    def _page_key(self, query: SearchQuery, page: int) -> str:
        return json.dumps({"target": query.target, "query": query.text, "page": page}, ensure_ascii=False, sort_keys=True)

    def collect(
        self,
        targets: list[str],
        max_pages: int = 3,
        per_page: int = 50,
        fetch_code_content: bool = False,
        fetch_issue_comments: bool = True,
        resume: bool = False,
        checkpoint_path: str | None = None,
    ) -> list[Finding]:
        queries = build_queries(self.config, targets)
        checkpoint_file = checkpoint_path or str(self.storage.normalized_dir / "collect_checkpoint.json")
        findings = self.storage.load_findings() if resume else []
        had_errors = False
        if findings and resume:
            print(f"Loaded {len(findings)} existing findings from previous run", flush=True)
        elif not resume:
            self.storage.overwrite_findings_jsonl([])

        seen_keys: set[tuple[str, str]] = {(finding.source_type, finding.html_url) for finding in findings}
        checkpoint = self.storage.load_checkpoint(checkpoint_file) if resume else {"completed_pages": []}
        completed_pages = set(checkpoint.get("completed_pages", []))
        print(f"Built {len(queries)} queries for targets={','.join(targets)}", flush=True)

        for query_index, query in enumerate(queries, start=1):
            print(f"[query {query_index}/{len(queries)}] target={query.target} q={query.text}", flush=True)
            for page in range(1, max_pages + 1):
                page_key = self._page_key(query, page)
                if page_key in completed_pages:
                    print(f"  [page {page}/{max_pages}] already completed in checkpoint, skipping", flush=True)
                    continue

                if query.target in {"issues", "pulls"}:
                    try:
                        payload = self.client.search_issues(query.text, page=page, per_page=per_page)
                    except GitHubApiError as exc:
                        had_errors = True
                        self.storage.append_error(
                            {"target": query.target, "query": query.text, "page": page, "error": str(exc)}
                        )
                        print(f"  [page {page}/{max_pages}] failed: {exc}", flush=True)
                        continue
                    self.storage.append_raw("issues_search", {"query": query.text, "page": page, "payload": payload})
                    items = payload.get("items", [])
                    print(
                        f"  [page {page}/{max_pages}] issues_api returned {len(items)} items; unique_findings={len(findings)}",
                        flush=True,
                    )
                    for item in items:
                        comments: list[str] = []
                        if fetch_issue_comments and item.get("comments", 0) > 0 and item.get("comments_url"):
                            try:
                                comments_payload = self.client.get_json_url(item["comments_url"])
                                comments = [comment.get("body", "") for comment in comments_payload]
                            except GitHubApiError as exc:
                                had_errors = True
                                self.storage.append_error(
                                    {
                                        "target": query.target,
                                        "query": query.text,
                                        "page": page,
                                        "item_url": item.get("html_url"),
                                        "comments_url": item.get("comments_url"),
                                        "error": str(exc),
                                    }
                                )
                                print(
                                    f"    [warn] failed to fetch comments for {item.get('html_url')}: {exc}",
                                    flush=True,
                                )
                        finding = _normalize_issue_item(item, query, self.config, comments)
                        dedupe_key = (finding.source_type, finding.html_url)
                        if dedupe_key not in seen_keys:
                            findings.append(finding)
                            seen_keys.add(dedupe_key)
                            self.storage.append_finding(finding)
                elif query.target == "code":
                    try:
                        payload = self.client.search_code(query.text, page=page, per_page=per_page)
                    except GitHubApiError as exc:
                        had_errors = True
                        self.storage.append_error(
                            {"target": query.target, "query": query.text, "page": page, "error": str(exc)}
                        )
                        print(f"  [page {page}/{max_pages}] failed: {exc}", flush=True)
                        continue
                    self.storage.append_raw("code_search", {"query": query.text, "page": page, "payload": payload})
                    items = payload.get("items", [])
                    print(
                        f"  [page {page}/{max_pages}] code_api returned {len(items)} items; unique_findings={len(findings)}",
                        flush=True,
                    )
                    for item in items:
                        content = ""
                        if fetch_code_content:
                            repo_full_name = item["repository"]["full_name"]
                            owner, repo = repo_full_name.split("/", 1)
                            try:
                                content = self.client.get_repo_file_content(owner, repo, item["path"])
                            except GitHubApiError as exc:
                                had_errors = True
                                self.storage.append_error(
                                    {
                                        "target": query.target,
                                        "query": query.text,
                                        "page": page,
                                        "item_url": item.get("html_url"),
                                        "path": item.get("path"),
                                        "error": str(exc),
                                    }
                                )
                                print(
                                    f"    [warn] failed to fetch file content for {item.get('html_url')}: {exc}",
                                    flush=True,
                                )
                        finding = _normalize_code_item(item, query, self.config, content)
                        dedupe_key = (finding.source_type, finding.html_url)
                        if dedupe_key not in seen_keys:
                            findings.append(finding)
                            seen_keys.add(dedupe_key)
                            self.storage.append_finding(finding)
                if not payload.get("items"):
                    print(f"  [page {page}/{max_pages}] empty page, stop paging this query", flush=True)
                    completed_pages.add(page_key)
                    checkpoint["completed_pages"] = sorted(completed_pages)
                    self.storage.save_checkpoint(checkpoint_file, checkpoint)
                    break
                completed_pages.add(page_key)
                checkpoint["completed_pages"] = sorted(completed_pages)
                self.storage.save_checkpoint(checkpoint_file, checkpoint)

        self.storage.write_findings(findings)
        if checkpoint_file and not had_errors:
            self.storage.remove_checkpoint(checkpoint_file)
        if had_errors:
            print(f"Finished collection with some errors. checkpoint kept at {checkpoint_file}", flush=True)
        print(f"Finished collection. unique_findings={len(findings)}", flush=True)
        return findings
