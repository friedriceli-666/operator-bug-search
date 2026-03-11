from pathlib import Path

from operator_bug_search.config import SearchConfig
from operator_bug_search.github_client import GitHubApiError
from operator_bug_search.pipeline import GitHubCollectionPipeline
from operator_bug_search.pipeline import _extract_code_snippets, _find_matches
from operator_bug_search.storage import Storage


def test_find_matches_case_insensitive() -> None:
    text = "A100 hits Wrong Result with cuDNN"
    assert _find_matches(text, ["a100", "v100"]) == ["a100"]
    assert _find_matches(text, ["wrong result", "nan"]) == ["wrong result"]


def test_extract_code_snippets() -> None:
    body = """
Issue body.

```python
import torch
assert x == y
```
"""
    snippets = _extract_code_snippets(body)
    assert len(snippets) == 1
    assert "import torch" in snippets[0]


class _FakeClient:
    def __init__(self, fail_pages: set[int] | None = None) -> None:
        self.calls: list[tuple[str, str, int]] = []
        self.fail_pages = fail_pages or set()

    def search_issues(self, query: str, page: int, per_page: int = 100) -> dict:
        self.calls.append(("issues", query, page))
        if page in self.fail_pages:
            raise GitHubApiError("temporary failure")
        return {
            "items": [
                {
                    "id": page,
                    "html_url": f"https://github.com/o/r/issues/{page}",
                    "url": f"https://api.github.com/repos/o/r/issues/{page}",
                    "repository_url": "https://api.github.com/repos/o/r",
                    "title": f"A100 wrong result page {page}",
                    "body": "```python\nimport torch\n```",
                    "state": "open",
                    "labels": [],
                    "comments": 0,
                }
            ]
        }


def test_resume_uses_checkpoint_and_keeps_partial_progress(tmp_path: Path) -> None:
    config = SearchConfig(
        gpu_models=["A100"],
        bug_keywords=["wrong result"],
        stack_keywords=["cuda"],
        queries_per_gpu=1,
    )
    storage = Storage(tmp_path)
    checkpoint_path = tmp_path / "normalized" / "checkpoint.json"

    client1 = _FakeClient(fail_pages={1})
    pipeline1 = GitHubCollectionPipeline(client=client1, storage=storage, config=config)
    findings1 = pipeline1.collect(
        targets=["issues"],
        max_pages=2,
        per_page=10,
        fetch_issue_comments=False,
        resume=True,
        checkpoint_path=str(checkpoint_path),
    )
    assert len(findings1) == 1
    assert checkpoint_path.exists()

    client2 = _FakeClient()
    pipeline2 = GitHubCollectionPipeline(client=client2, storage=storage, config=config)
    findings2 = pipeline2.collect(
        targets=["issues"],
        max_pages=2,
        per_page=10,
        fetch_issue_comments=False,
        resume=True,
        checkpoint_path=str(checkpoint_path),
    )
    assert len(findings2) == 2
    assert not checkpoint_path.exists()
