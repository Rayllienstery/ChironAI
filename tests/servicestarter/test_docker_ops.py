"""Tests for docker_ops helpers."""

from __future__ import annotations

from unittest.mock import patch

from servicestarter.docker_ops import (
    container_name_matches_running,
    open_webui_port_from_url,
    qdrant_port_from_url,
)


def test_qdrant_port_from_url() -> None:
    assert qdrant_port_from_url("http://localhost:6333") == 6333
    assert qdrant_port_from_url("http://example.com:7777") == 7777


def test_open_webui_port_from_url() -> None:
    assert open_webui_port_from_url("http://localhost:3000") == 3000


def test_container_name_matches_running_true() -> None:
    with patch("servicestarter.docker_ops.run_docker", return_value=(0, "open-webui-foo", "")):
        assert container_name_matches_running("open-webui") is True


def test_container_name_matches_running_false() -> None:
    with patch("servicestarter.docker_ops.run_docker", return_value=(0, "", "")):
        assert container_name_matches_running("qdrant") is False
