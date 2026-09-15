from __future__ import annotations

from types import SimpleNamespace

from application.windows_idle import (
    _IdlePulseToken,
    begin_proxy_activity,
    end_proxy_activity,
    is_rag_fusion_generation_request,
    pulse_idle_timers,
    register_rag_fusion_idle_pulses,
)


def test_generation_request_matcher_only_posts_known_paths() -> None:
    assert is_rag_fusion_generation_request("POST", "/v1/chat/completions") is True
    assert is_rag_fusion_generation_request("POST", "/v1/messages?x=1") is True
    assert is_rag_fusion_generation_request("GET", "/v1/chat/completions") is False
    assert is_rag_fusion_generation_request("POST", "/v1/models") is False


def test_pulse_idle_timers_is_noop_off_windows(monkeypatch) -> None:
    monkeypatch.setattr("application.windows_idle.sys.platform", "linux")
    pulse_idle_timers()


def test_idle_token_end_is_idempotent(monkeypatch) -> None:
    calls: list[str] = []
    monkeypatch.setattr("application.windows_idle.end_proxy_activity", lambda: calls.append("end"))
    token = _IdlePulseToken()
    token.end()
    token.end()
    assert calls == ["end"]


def test_begin_and_end_proxy_activity_start_heartbeat(monkeypatch) -> None:
    pulses: list[str] = []
    monkeypatch.setattr("application.windows_idle.pulse_idle_timers", lambda: pulses.append("pulse"))
    monkeypatch.setattr("application.windows_idle._PULSE_INTERVAL_SEC", 0.01)
    begin_proxy_activity()
    end_proxy_activity()
    assert pulses


def test_register_idle_pulses_skips_non_generation(monkeypatch) -> None:
    hooks: dict[str, object] = {}

    class FakeApp:
        def before_request(self, fn):
            hooks["before"] = fn
            return fn

        def after_request(self, fn):
            hooks["after"] = fn
            return fn

        def teardown_request(self, fn):
            hooks["teardown"] = fn
            return fn

    monkeypatch.setattr("application.windows_idle.request", SimpleNamespace(method="GET", path="/health"))
    fake_g = SimpleNamespace()
    monkeypatch.setattr("application.windows_idle.g", fake_g)
    register_rag_fusion_idle_pulses(FakeApp())
    hooks["before"]()
    assert not hasattr(fake_g, "chiron_idle_token")
    response = SimpleNamespace(call_on_close=None)
    assert hooks["after"](response) is response


def test_register_idle_pulses_hooks_generation_requests(monkeypatch) -> None:
    hooks: dict[str, object] = {}
    calls: list[str] = []

    class FakeApp:
        def before_request(self, fn):
            hooks["before"] = fn
            return fn

        def after_request(self, fn):
            hooks["after"] = fn
            return fn

        def teardown_request(self, fn):
            hooks["teardown"] = fn
            return fn

    monkeypatch.setattr(
        "application.windows_idle.request",
        SimpleNamespace(method="POST", path="/v1/chat/completions"),
    )
    fake_g = SimpleNamespace()
    monkeypatch.setattr("application.windows_idle.g", fake_g)
    monkeypatch.setattr("application.windows_idle.begin_proxy_activity", lambda: calls.append("begin"))
    monkeypatch.setattr("application.windows_idle.end_proxy_activity", lambda: calls.append("end"))
    register_rag_fusion_idle_pulses(FakeApp())
    hooks["before"]()
    assert calls == ["begin"]
    closed: list[object] = []
    response = SimpleNamespace(call_on_close=lambda cb: closed.append(cb) or cb())
    assert hooks["after"](response) is response
    assert "end" in calls
    hooks["teardown"](None)
