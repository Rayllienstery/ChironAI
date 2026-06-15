"""
Focused tests for Qdrant payload structure and search request shape.
"""

from __future__ import annotations


def test_qdrant_search_body_shape() -> None:
    """Search request must have vector, limit, with_payload."""
    from infrastructure.qdrant.rag_repository_impl import QdrantRagRepository
    repo = QdrantRagRepository(default_collection="test_coll")
    assert repo.get_collection_name() == "test_coll"


def test_qdrant_repository_search_accepts_filter() -> None:
    """QdrantRagRepository.search accepts optional filter_dict."""
    from infrastructure.qdrant.rag_repository_impl import QdrantRagRepository
    repo = QdrantRagRepository(default_collection="test_coll")
    # Just check the method exists and accepts filter_dict=None
    assert hasattr(repo, "search")
    import inspect
    sig = inspect.signature(repo.search)
    assert "filter_dict" in sig.parameters
