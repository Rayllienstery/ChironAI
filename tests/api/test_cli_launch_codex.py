from __future__ import annotations

from types import SimpleNamespace


def test_resolve_default_codex_model_prefers_first_build_id_when_proxy_model_not_build(monkeypatch) -> None:
    import api.cli.__main__ as cli

    class FakeRepo:
        def get_app_setting(self, key: str):
            if key == "proxy_model":
                return "devstral-small-2:24b-cloud"
            if key == "llm_proxy_builds":
                return '[{"id":"Hard-worker"},{"id":"Researcher"}]'
            if key == "proxy_settings":
                return '{"model":"devstral-small-2:24b-cloud"}'
            return None

    monkeypatch.setattr(
        "infrastructure.database.settings_repository.get_settings_repository",
        lambda: FakeRepo(),
        raising=False,
    )
    assert cli._resolve_default_codex_model() == "Hard-worker"


def test_resolve_default_codex_model_uses_proxy_model_if_it_is_build_id(monkeypatch) -> None:
    import api.cli.__main__ as cli

    class FakeRepo:
        def get_app_setting(self, key: str):
            if key == "proxy_model":
                return "Researcher"
            if key == "llm_proxy_builds":
                return '[{"id":"Hard-worker"},{"id":"Researcher"}]'
            if key == "proxy_settings":
                return '{"model":"devstral-small-2:24b-cloud"}'
            return None

    monkeypatch.setattr(
        "infrastructure.database.settings_repository.get_settings_repository",
        lambda: FakeRepo(),
        raising=False,
    )
    assert cli._resolve_default_codex_model() == "Researcher"


def test_resolve_default_codex_model_empty_when_no_builds(monkeypatch) -> None:
    import api.cli.__main__ as cli

    class FakeRepo:
        def get_app_setting(self, key: str):
            if key == "proxy_model":
                return "devstral-small-2:24b-cloud"
            if key == "llm_proxy_builds":
                return ""
            if key == "proxy_settings":
                return '{"model":"devstral-small-2:24b-cloud"}'
            return None

    monkeypatch.setattr(
        "infrastructure.database.settings_repository.get_settings_repository",
        lambda: FakeRepo(),
        raising=False,
    )
    assert cli._resolve_default_codex_model() == ""


def test_cmd_launch_codex_prefers_explicit_model(monkeypatch, tmp_path) -> None:
    import api.cli.__main__ as cli

    captured: dict[str, object] = {"calls": []}

    monkeypatch.setattr(cli, "_find_real_codex_executable", lambda shim_path=None: r"C:\tools\codex.cmd")
    monkeypatch.setattr(cli, "_resolve_default_codex_model", lambda: "from-settings")

    def _fake_run(argv, cwd=None, env=None, **_kwargs):
        captured["calls"].append(
            {
                "argv": list(argv),
                "cwd": cwd,
                "env": dict(env or {}),
            }
        )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)

    ns = SimpleNamespace(
        base_url="http://127.0.0.1:8080",
        api_key="ChironAI",
        working_dir=str(tmp_path),
        model="explicit-build",
        profile="",
        codex_args=[],
        shim_path=None,
    )
    rc = cli.cmd_launch_codex(ns)
    assert rc == 0
    assert len(captured["calls"]) == 1
    launch_call = captured["calls"][0]
    argv = launch_call["argv"]
    assert "--model" in argv
    assert "explicit-build" in argv
    assert "-c" in argv
    assert any(str(v).startswith('model_provider="chironai-launch"') for v in argv)
    assert any(str(v).startswith('model_providers.chironai-launch.base_url=') for v in argv)
    assert 'model_providers.chironai-launch.name="Ollama"' in argv
    assert 'model_providers.chironai-launch.wire_api="responses"' in argv
    assert launch_call["cwd"] == str(tmp_path)
    assert launch_call["env"]["OPENAI_BASE_URL"] == "http://127.0.0.1:8080/v1"
    assert launch_call["env"]["OPENAI_API_KEY"] == "ChironAI"


def test_cmd_launch_codex_uses_resolved_default_model(monkeypatch, tmp_path) -> None:
    import api.cli.__main__ as cli

    captured: dict[str, object] = {"calls": []}

    monkeypatch.setattr(cli, "_find_real_codex_executable", lambda shim_path=None: r"C:\tools\codex.cmd")
    monkeypatch.setattr(cli, "_resolve_default_codex_model", lambda: "model-from-settings")

    def _fake_run(argv, **_kwargs):
        captured["calls"].append({"argv": list(argv)})
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)

    ns = SimpleNamespace(
        base_url="http://127.0.0.1:8080",
        api_key="ChironAI",
        working_dir=str(tmp_path),
        model="",
        profile="",
        codex_args=[],
        shim_path=None,
    )
    rc = cli.cmd_launch_codex(ns)
    assert rc == 0
    assert len(captured["calls"]) == 1
    argv = captured["calls"][0]["argv"]
    model_index = argv.index("--model")
    assert argv[model_index + 1] == "model-from-settings"
    assert any(str(v).startswith('model_provider="chironai-launch"') for v in argv)


def test_build_codex_proxy_overrides_contains_provider_and_api_mode() -> None:
    import api.cli.__main__ as cli

    overrides = cli._build_codex_proxy_overrides("http://127.0.0.1:8080")
    assert "-c" in overrides
    assert 'model_provider="chironai-launch"' in overrides
    assert 'model_providers.chironai-launch.name="Ollama"' in overrides
    assert 'model_providers.chironai-launch.base_url="http://127.0.0.1:8080/v1/"' in overrides
    assert 'model_providers.chironai-launch.wire_api="responses"' in overrides
    assert 'openai_base_url="http://127.0.0.1:8080/v1/"' in overrides


def test_cmd_launch_codex_errors_when_no_model_and_no_builds(monkeypatch, tmp_path) -> None:
    import api.cli.__main__ as cli

    monkeypatch.setattr(cli, "_find_real_codex_executable", lambda shim_path=None: r"C:\tools\codex.cmd")
    monkeypatch.setattr(cli, "_resolve_default_codex_model", lambda: "")

    called = {"run": False}

    def _fake_run(*_args, **_kwargs):
        called["run"] = True
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)

    ns = SimpleNamespace(
        base_url="http://127.0.0.1:8080",
        api_key="ChironAI",
        working_dir=str(tmp_path),
        model="",
        profile="",
        codex_args=[],
        shim_path=None,
    )
    rc = cli.cmd_launch_codex(ns)
    assert rc == 1
    assert called["run"] is False


def test_find_real_codex_executable_skips_shim(monkeypatch) -> None:
    import api.cli.__main__ as cli

    shim = r"C:\Users\me\.chironai\bin\codex.cmd"

    def _fake_run(argv, capture_output=None, text=None, timeout=None):  # noqa: ARG001
        assert argv[:3] == ["cmd", "/c", "where"]
        return SimpleNamespace(returncode=0, stdout=shim + "\nC:\\Users\\me\\AppData\\Roaming\\npm\\codex.cmd\n")

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)
    monkeypatch.setattr(cli, "_is_launchable_binary", lambda _p: True)
    out = cli._find_real_codex_executable(shim_path=shim)
    assert out == r"C:\Users\me\AppData\Roaming\npm\codex.cmd"


def test_find_real_codex_executable_skips_non_launchable_candidate(monkeypatch) -> None:
    import api.cli.__main__ as cli

    shim = r"C:\Users\me\.chironai\bin\codex.cmd"

    def _fake_run(argv, capture_output=None, text=None, timeout=None):  # noqa: ARG001
        # Simulate cursor exe first, npm cmd second.
        if argv[:3] == ["cmd", "/c", "where"] and argv[3] == "codex.cmd":
            return SimpleNamespace(returncode=0, stdout=r"C:\Users\me\AppData\Roaming\npm\codex.cmd" + "\n")
        if argv[:3] == ["cmd", "/c", "where"] and argv[3] == "codex":
            return SimpleNamespace(returncode=0, stdout=r"C:\tooling\cursor\codex.exe" + "\n")
        return SimpleNamespace(returncode=1, stdout="", stderr="")

    monkeypatch.setattr(cli.subprocess, "run", _fake_run)

    def _probe(path: str) -> bool:
        # reject cursor exe, accept npm cmd
        return path.lower().endswith("npm\\codex.cmd")

    monkeypatch.setattr(cli, "_is_launchable_binary", _probe)
    out = cli._find_real_codex_executable(shim_path=shim)
    assert out == r"C:\Users\me\AppData\Roaming\npm\codex.cmd"
