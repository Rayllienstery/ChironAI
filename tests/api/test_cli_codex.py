from __future__ import annotations

import pytest


def test_cli_codex_parser_accepts_model_config_and_extra_args(monkeypatch: pytest.MonkeyPatch) -> None:
    import api.cli.__main__ as cli

    captured: dict[str, object] = {}

    def fake_cmd_codex(ns):
        captured["model"] = ns.model
        captured["config"] = ns.config
        captured["extra_args"] = ns.extra_args
        return 0

    monkeypatch.setattr(cli, "cmd_codex", fake_cmd_codex)
    monkeypatch.setattr(
        "sys.argv",
        ["chironai", "codex", "--model", "Agent-high", "--config", "--", "--sandbox", "workspace-write"],
    )

    with pytest.raises(SystemExit) as exc:
        cli.main()

    assert exc.value.code == 0
    assert captured == {
        "model": "Agent-high",
        "config": True,
        "extra_args": ["--", "--sandbox", "workspace-write"],
    }
