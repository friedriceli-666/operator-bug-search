from __future__ import annotations

from dataclasses import dataclass

from .config import SearchConfig


@dataclass(slots=True)
class SearchQuery:
    target: str
    text: str


def _quote_if_needed(value: str) -> str:
    return f"\"{value}\"" if " " in value else value


def build_queries(config: SearchConfig, targets: list[str]) -> list[SearchQuery]:
    queries: list[SearchQuery] = []
    bug_keywords = config.bug_keywords[: config.queries_per_gpu]
    stack_segment = " OR ".join(_quote_if_needed(item) for item in config.stack_keywords[:4])

    for gpu in config.gpu_models:
        for bug_keyword in bug_keywords:
            text = " ".join(
                [
                    _quote_if_needed(gpu),
                    _quote_if_needed(bug_keyword),
                    f"({stack_segment})",
                ]
            )
            for target in targets:
                if target == "issues":
                    queries.append(SearchQuery(target="issues", text=f"{text} type:issue"))
                elif target == "pulls":
                    queries.append(SearchQuery(target="pulls", text=f"{text} type:pr"))
                elif target == "code":
                    queries.append(SearchQuery(target="code", text=text))
    return queries
