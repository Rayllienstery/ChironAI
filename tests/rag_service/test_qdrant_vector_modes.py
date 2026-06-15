"""Qdrant collection vector modes (named dense + hybrid only)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import httpx
import pytest
from rag_service.domain.errors import RetrievalError
from rag_service.infrastructure.qdrant_repository import QdrantRagRepository


def _collection_get_response(*, sparse: bool = False, named_dense: bool = False) -> dict[str, Any]:
    params: dict[str, Any] = {"vectors": [128]}
    if named_dense:
        params = {"vectors": {"dense": {"size": 128, "distance": "Cosine"}}}
    if sparse:
        params["sparse_vectors"] = {"sparse": {}}
    return {"result": {"config": {"params": params}}}


def test_collection_vector_mode_hybrid() -> None:
    repo = QdrantRagRepository(base_url="http://qdrant:6333", explicit_collection="hybrid_coll")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _collection_get_response(sparse=True)
    with patch("rag_service.infrastructure.qdrant_repository.httpx.get", return_value=mock_resp):
        assert repo._collection_vector_mode() == "hybrid"
        assert repo.supports_hybrid() is True


def test_collection_vector_mode_named_dense() -> None:
    repo = QdrantRagRepository(base_url="http://qdrant:6333", explicit_collection="dense_named")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _collection_get_response(named_dense=True)
    with patch("rag_service.infrastructure.qdrant_repository.httpx.get", return_value=mock_resp):
        assert repo._collection_vector_mode() == "named_dense"


def test_collection_vector_mode_rejects_unnamed_schema() -> None:
    repo = QdrantRagRepository(base_url="http://qdrant:6333", explicit_collection="old")
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = _collection_get_response()
    with patch("rag_service.infrastructure.qdrant_repository.httpx.get", return_value=mock_resp):
        with pytest.raises(RetrievalError, match="named 'dense'"):
            repo._collection_vector_mode()


def test_collection_vector_mode_raises_on_collection_error() -> None:
    repo = QdrantRagRepository(base_url="http://qdrant:6333", explicit_collection="missing")
    with patch(
        "rag_service.infrastructure.qdrant_repository.httpx.get",
        side_effect=httpx.RequestError("down"),
    ):
        with pytest.raises(RetrievalError, match="Failed to read Qdrant collection"):
            repo._collection_vector_mode()


def test_search_dense_only_uses_named_vector() -> None:
    repo = QdrantRagRepository(base_url="http://qdrant:6333", explicit_collection="coll")
    repo._mode_cache_coll = "coll"
    repo._mode_cache = "named_dense"

    bodies: list[dict[str, Any]] = []

    def fake_post(url: str, json: dict[str, Any] | None = None, timeout: float = 30) -> MagicMock:
        assert json is not None
        bodies.append(dict(json))
        ok = MagicMock()
        ok.raise_for_status = MagicMock()
        ok.json.return_value = {"result": []}
        return ok

    with patch("rag_service.infrastructure.qdrant_repository.httpx.post", side_effect=fake_post):
        repo._search_dense_only("coll", [0.1, 0.2], 3, None)

    assert bodies[0]["vector"] == {"name": "dense", "vector": [0.1, 0.2]}


def test_search_dense_only_no_legacy_fallback_on_http_error() -> None:
    repo = QdrantRagRepository(base_url="http://qdrant:6333", explicit_collection="coll")
    repo._mode_cache_coll = "coll"
    repo._mode_cache = "named_dense"

    err_resp = MagicMock()
    err_resp.text = "bad request"
    http_err = httpx.HTTPStatusError("400", request=MagicMock(), response=err_resp)

    with patch(
        "rag_service.infrastructure.qdrant_repository.httpx.post",
        side_effect=http_err,
    ):
        with pytest.raises(RetrievalError, match="Qdrant search error"):
            repo._search_dense_only("coll", [0.1], 2, None)


def test_search_hybrid_falls_back_to_dense_on_query_http_error() -> None:
    repo = QdrantRagRepository(base_url="http://qdrant:6333", explicit_collection="coll")
    repo._mode_cache_coll = "coll"
    repo._mode_cache = "hybrid"

    err_resp = MagicMock()
    err_resp.text = "query failed"
    http_err = httpx.HTTPStatusError("400", request=MagicMock(), response=err_resp)

    ok_resp = MagicMock()
    ok_resp.raise_for_status = MagicMock()
    ok_resp.json.return_value = {"result": [{"id": 2, "score": 0.5, "payload": {"k": "v"}}]}

    def fake_post(url: str, json: dict[str, Any] | None = None, timeout: float = 45) -> MagicMock:
        if "/points/query" in url:
            raise http_err
        return ok_resp

    with patch("rag_service.infrastructure.qdrant_repository.httpx.post", side_effect=fake_post):
        hits = repo._search_hybrid("coll", [0.1], [0], [1.0], 2, None)

    assert len(hits) == 1
    assert hits[0]["payload"] == {"k": "v"}
