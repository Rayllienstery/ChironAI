from __future__ import annotations

from infrastructure.qdrant.collection_names import list_collection_names


def test_list_collection_names_parses_qdrant_response(monkeypatch) -> None:
    class _Response:
        ok = True

        @staticmethod
        def json() -> dict[str, object]:
            return {"result": {"collections": [{"name": "docs"}, {"name": "apple"}]}}

    monkeypatch.setattr(
        "infrastructure.qdrant.collection_names.requests.get",
        lambda url, timeout=5.0: _Response(),
    )
    monkeypatch.setattr(
        "infrastructure.qdrant.collection_names.get_qdrant_url",
        lambda: "http://127.0.0.1:6333",
    )

    assert list_collection_names() == ["docs", "apple"]


def test_list_collection_names_returns_empty_on_failure(monkeypatch) -> None:
    def _boom(*args, **kwargs):
        raise TimeoutError("unreachable")

    monkeypatch.setattr("infrastructure.qdrant.collection_names.requests.get", _boom)
    monkeypatch.setattr(
        "infrastructure.qdrant.collection_names.get_qdrant_url",
        lambda: "http://127.0.0.1:6333",
    )

    assert list_collection_names() == []
