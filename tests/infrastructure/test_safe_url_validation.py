"""Tests for safe URL validation in DockerManager and LlmProxy."""

from __future__ import annotations

import pytest
from docker_manager.manager import DockerManager
from llm_proxy.chat_completions_ollama_proxy import _qdrant_collection_names_cached


def test_docker_manager_wait_http_rejects_file_url() -> None:
    dm = DockerManager()
    with pytest.raises(ValueError, match="url must use http:// or https:// scheme"):
        dm.wait_http("file:///etc/passwd")


def test_docker_manager_wait_http_rejects_invalid_scheme() -> None:
    dm = DockerManager()
    with pytest.raises(ValueError, match="url must use http:// or https:// scheme"):
        dm.wait_http("ftp://example.com")


def test_docker_manager_wait_http_accepts_http() -> None:
    dm = DockerManager()
    # Should not raise on scheme validation; actual request will fail quickly.
    result = dm.wait_http("http://127.0.0.1:1", timeout=0.1, interval=0.05)
    assert result["ok"] is False
    assert result["url"] == "http://127.0.0.1:1/"


def test_qdrant_collection_names_cached_rejects_file_url() -> None:
    names, error = _qdrant_collection_names_cached("file:///etc/passwd")
    assert names == set()
    assert error == "qdrant_url_invalid_scheme"


def test_qdrant_collection_names_cached_rejects_ftp() -> None:
    names, error = _qdrant_collection_names_cached("ftp://qdrant:6333")
    assert names == set()
    assert error == "qdrant_url_invalid_scheme"
