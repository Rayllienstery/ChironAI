"""Tests for stable sparse text hashing."""

from __future__ import annotations

from infrastructure.rag.sparse_text import text_to_sparse_vector


def test_text_to_sparse_vector_stable() -> None:
    i1, v1 = text_to_sparse_vector("Swift MVVM Observable")
    i2, v2 = text_to_sparse_vector("Swift MVVM Observable")
    assert i1 == i2 and v1 == v2
    assert len(i1) == len(v1)


def test_empty_text_sparse() -> None:
    assert text_to_sparse_vector("") == ([], [])
