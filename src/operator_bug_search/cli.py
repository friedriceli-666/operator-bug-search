from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .config import SearchConfig
from .github_client import GitHubApiError, GitHubClient
from .pipeline import GitHubCollectionPipeline
from .storage import Storage


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect GitHub bug reports related to GPU operator errors.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect = subparsers.add_parser("collect", help="Collect issues, PRs, and code matches from GitHub.")
    collect.add_argument("--config", required=True, help="Path to search config json.")
    collect.add_argument("--output-dir", default="data", help="Output directory.")
    collect.add_argument("--targets", default="issues,pulls,code", help="Comma separated targets.")
    collect.add_argument("--max-pages", type=int, default=3, help="Pages per query.")
    collect.add_argument("--per-page", type=int, default=50, help="Items per page.")
    collect.add_argument("--fetch-code-content", action="store_true", help="Fetch full file content for code matches.")
    collect.add_argument("--resume", action="store_true", help="Resume from an existing checkpoint and findings jsonl.")
    collect.add_argument("--checkpoint-file", default=None, help="Optional checkpoint file path.")
    collect.add_argument(
        "--skip-issue-comments",
        action="store_true",
        help="Do not fetch issue comments.",
    )
    collect.add_argument("--token", default=os.getenv("GITHUB_TOKEN"), help="GitHub token. Defaults to GITHUB_TOKEN.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv or sys.argv[1:])
    if args.command != "collect":
        return 1

    config = SearchConfig.from_file(args.config)
    storage = Storage(Path(args.output_dir))
    client = GitHubClient(token=args.token)
    pipeline = GitHubCollectionPipeline(client=client, storage=storage, config=config)
    targets = [part.strip() for part in args.targets.split(",") if part.strip()]
    print(
        f"Starting collection with targets={targets}, max_pages={args.max_pages}, per_page={args.per_page}, "
        f"fetch_code_content={args.fetch_code_content}, fetch_issue_comments={not args.skip_issue_comments}, "
        f"resume={args.resume}",
        flush=True,
    )

    try:
        findings = pipeline.collect(
            targets=targets,
            max_pages=args.max_pages,
            per_page=args.per_page,
            fetch_code_content=args.fetch_code_content,
            fetch_issue_comments=not args.skip_issue_comments,
            resume=args.resume,
            checkpoint_path=args.checkpoint_file,
        )
    except GitHubApiError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    print(f"Collected {len(findings)} unique findings into {Path(args.output_dir).resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
