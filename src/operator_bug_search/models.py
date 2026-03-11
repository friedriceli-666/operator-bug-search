from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass(slots=True)
class Finding:
    source_type: str
    github_id: int
    html_url: str
    api_url: str
    repo_full_name: str
    title: str
    body: str
    state: str
    labels: list[str] = field(default_factory=list)
    matched_gpu_models: list[str] = field(default_factory=list)
    matched_bug_keywords: list[str] = field(default_factory=list)
    suspected_stack: list[str] = field(default_factory=list)
    has_repro_code: bool = False
    code_snippets: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    query: str = ""
    collected_at: str = ""
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)
