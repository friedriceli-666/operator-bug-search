from operator_bug_search.config import SearchConfig
from operator_bug_search.query_builder import build_queries


def test_build_queries_covers_all_targets() -> None:
    config = SearchConfig(
        gpu_models=["A100"],
        bug_keywords=["wrong result", "accuracy"],
        stack_keywords=["cuda", "pytorch"],
        queries_per_gpu=2,
    )
    queries = build_queries(config, ["issues", "pulls", "code"])
    assert len(queries) == 6
    assert any(query.target == "issues" and "type:issue" in query.text for query in queries)
    assert any(query.target == "pulls" and "type:pr" in query.text for query in queries)
    assert any(query.target == "code" and "A100" in query.text for query in queries)
