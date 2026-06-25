"""Tests for safe URL validation helpers used by WebUI backend."""

from __future__ import annotations

import pytest

from webui_backend.open_browser_when_ready import _safe_local_url


def test_safe_local_url_accepts_localhost() -> None:
    assert _safe_local_url(8080, "/webui") == "http://127.0.0.1:8080/webui"


def test_safe_local_url_rejects_non_local() -> None:
    with pytest.raises(ValueError, match="path contains invalid characters"):
        _safe_local_url(8080, "//evil.com/")


def test_safe_local_url_rejects_file_scheme() -> None:
    with pytest.raises(ValueError, match="path contains invalid characters"):
        _safe_local_url(8080, "/etc/passwd?x=1")
