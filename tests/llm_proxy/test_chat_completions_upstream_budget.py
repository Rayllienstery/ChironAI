from __future__ import annotations

from llm_proxy.chat_completions_upstream_budget import (
    compact_upstream_messages_for_budget,
    resolve_upstream_json_cap,
)


def test_resolve_upstream_json_cap_clamps_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROXY_UPSTREAM_MESSAGES_JSON_CAP", "99999999")
    assert resolve_upstream_json_cap(None) == 2_000_000


def test_resolve_upstream_json_cap_honors_input_budget(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROXY_UPSTREAM_MESSAGES_JSON_CAP", "500000")
    cap = resolve_upstream_json_cap({"input_budget_json_chars": 300000})
    assert cap == 300000


def test_compact_upstream_messages_for_budget_adds_budget_fields() -> None:
    messages = [{"role": "user", "content": "hello"}]
    compacted, diag = compact_upstream_messages_for_budget(
        messages,
        {
            "input_budget_json_chars": 500000,
            "reserved_output_tokens": 128,
            "safety_margin_tokens": 64,
            "input_budget_tokens": 4096,
        },
    )
    assert compacted == messages
    assert diag["reserved_output_tokens"] == 128
    assert diag["input_budget_tokens"] == 4096
