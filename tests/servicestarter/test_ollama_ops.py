"""Tests for Ollama HTTP ping helper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from servicestarter.ollama_ops import ollama_ping


def test_ollama_ping_ok() -> None:
    fake_resp = MagicMock()
    fake_resp.ok = True
    fake_resp.status_code = 200
    with patch("servicestarter.ollama_ops.requests.get", return_value=fake_resp):
        out = ollama_ping("http://localhost:11343", timeout=1.0)
    assert out["ok"] is True
    assert out["status_code"] == 200


def test_ollama_ping_connection_error() -> None:
    import requests

    with patch(
        "servicestarter.ollama_ops.requests.get",
        side_effect=requests.ConnectionError("nope"),
    ):
        out = ollama_ping("http://localhost:11343", timeout=1.0)
    assert out["ok"] is False
    assert "error" in out
