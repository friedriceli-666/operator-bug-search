from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class SearchConfig:
    gpu_models: list[str]
    bug_keywords: list[str]
    stack_keywords: list[str]
    queries_per_gpu: int = 6
    include_repo_keywords: list[str] | None = None

    @classmethod
    def from_file(cls, path: str | Path) -> "SearchConfig":
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            gpu_models=payload["gpu_models"],
            bug_keywords=payload["bug_keywords"],
            stack_keywords=payload["stack_keywords"],
            queries_per_gpu=payload.get("queries_per_gpu", 6),
            include_repo_keywords=payload.get("include_repo_keywords", []),
        )
