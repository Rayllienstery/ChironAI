from __future__ import annotations

from infrastructure.rag.qdrant_point_builder import (
    DENSE_VECTOR_NAME,
    build_named_vectors,
    dense_vectors_config,
)


def test_build_named_vectors_dense_only_is_named_dict() -> None:
    payload = build_named_vectors("hello", [0.1, 0.2], hybrid_sparse=False)
    assert payload == {DENSE_VECTOR_NAME: [0.1, 0.2]}


def test_dense_vectors_config_uses_named_dense() -> None:
    cfg = dense_vectors_config(384)
    assert DENSE_VECTOR_NAME in cfg
    assert cfg[DENSE_VECTOR_NAME].size == 384
