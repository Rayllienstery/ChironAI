"""Tests for Ollama subprocess runner (mocked CLI)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from infrastructure.ollama.cli_runner import (
    OllamaInteractorCliError,
    invoke_embed,
    invoke_json,
)


def test_invoke_json_success() -> None:
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = '{"embeddings": [[0.1, 0.2]]}'
    fake.stderr = ""
    with patch("infrastructure.ollama.cli_runner.subprocess.run", return_value=fake):
        out = invoke_json(["embed"], stdin_obj={"url": "http://x/api/embed", "json": {"model": "m", "input": "a"}})
    assert out["embeddings"] == [[0.1, 0.2]]


def test_invoke_json_cli_error() -> None:
    fake = MagicMock()
    fake.returncode = 1
    fake.stdout = ""
    fake.stderr = json.dumps({"error": "connection refused"})
    with patch("infrastructure.ollama.cli_runner.subprocess.run", return_value=fake):
        with pytest.raises(OllamaInteractorCliError, match="connection refused"):
            invoke_json(["embed"], stdin_obj={"url": "http://x", "json": {}})


def test_invoke_embed_delegates() -> None:
    fake = MagicMock()
    fake.returncode = 0
    fake.stdout = '{"embeddings": [[]]}'
    fake.stderr = ""
    with patch("infrastructure.ollama.cli_runner.subprocess.run", return_value=fake) as m:
        invoke_embed({"url": "http://h/api/embed", "json": {"model": "m", "input": "z"}, "timeout": 30})
    args, kwargs = m.call_args
    assert "embed" in args[0]
    assert "--timeout" in args[0]
    assert args[0][args[0].index("--timeout") + 1] == "30"
    assert json.loads(kwargs["input"])["url"] == "http://h/api/embed"


def test_invoke_embed_retries_on_transient_500(monkeypatch: pytest.MonkeyPatch) -> None:
    bad = MagicMock()
    bad.returncode = 1
    bad.stdout = ""
    bad.stderr = '{"error":"upstream","body":{"status_code":500}}'
    good = MagicMock()
    good.returncode = 0
    good.stdout = '{"embeddings": [[0.1]]}'
    good.stderr = ""
    with patch("infrastructure.ollama.cli_runner.subprocess.run", side_effect=[bad, good]) as m:
        monkeypatch.setattr("infrastructure.ollama.cli_runner.time.sleep", lambda s: None)
        out = invoke_embed(
            {"url": "http://h/api/embed", "json": {"model": "m", "input": "z"}, "timeout": 30},
            max_retries=2,
            retry_base_delay_sec=0.01,
        )
    assert out["embeddings"] == [[0.1]]
    assert m.call_count == 2
