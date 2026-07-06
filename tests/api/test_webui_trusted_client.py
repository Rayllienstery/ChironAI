"""Tests for loopback client checks on sensitive WebUI routes."""

from __future__ import annotations

import pytest
from flask import Flask, request

from api.http.webui_trusted_client import is_loopback_client_request


@pytest.mark.parametrize(
    "remote_addr",
    ["127.0.0.1", "::1", "127.0.0.2"],
)
def test_is_loopback_client_request_accepts_loopback(remote_addr: str) -> None:
    app = Flask(__name__)

    with app.test_request_context(environ_base={"REMOTE_ADDR": remote_addr}):
        assert is_loopback_client_request(request) is True


@pytest.mark.parametrize(
    "remote_addr",
    ["192.168.1.10", "10.0.0.5", "8.8.8.8", "", "not-an-ip"],
)
def test_is_loopback_client_request_rejects_non_loopback(remote_addr: str) -> None:
    app = Flask(__name__)

    with app.test_request_context(environ_base={"REMOTE_ADDR": remote_addr}):
        assert is_loopback_client_request(request) is False
