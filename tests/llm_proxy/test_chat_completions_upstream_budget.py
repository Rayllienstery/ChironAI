from __future__ import annotations

from llm_proxy.chat_completions_upstream_budget import (
    _conversation_tail_start_index,
    compact_upstream_messages_for_budget,
    resolve_upstream_json_cap,
)

_TINY_BUDGET = {
    "input_budget_json_chars": 8000,
    "reserved_output_tokens": 128,
    "safety_margin_tokens": 64,
    "input_budget_tokens": 2000,
}


def test_resolve_upstream_json_cap_clamps_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROXY_UPSTREAM_MESSAGES_JSON_CAP", "99999999")
    assert resolve_upstream_json_cap(None) == 4_194_304


def test_resolve_upstream_json_cap_honors_input_budget(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROXY_UPSTREAM_MESSAGES_JSON_CAP", "500000")
    cap = resolve_upstream_json_cap({"input_budget_json_chars": 300000})
    assert cap == 300000
    # Large flash/smart windows must raise the cap, not stay stuck at the 380K default.
    assert resolve_upstream_json_cap({"input_budget_json_chars": 1_048_576}) == 1_048_576
    assert resolve_upstream_json_cap({"input_budget_json_chars": 4_194_304}) == 4_194_304


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


def test_conversation_tail_starts_at_last_user() -> None:
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "old"},
        {"role": "user", "content": "second"},
        {"role": "assistant", "content": "draft"},
    ]
    assert _conversation_tail_start_index(messages) == 3


def test_compact_preserves_assistant_prefill_after_last_user() -> None:
    draft = "И ты прав по сути: были и те, кто " + ("ответ " * 20)
    messages = [
        {"role": "system", "content": "S" * 20_000},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": draft},
    ]
    compacted, diag = compact_upstream_messages_for_budget(messages, _TINY_BUDGET)
    assert compacted[-1]["content"] == draft
    assert "upstream budget" not in compacted[-1]["content"]
    assert diag.get("still_over_budget_after_history_compaction") is True


def test_compact_does_not_chop_short_prior_assistant_to_256() -> None:
    prior = "x" * 300
    messages = [
        {"role": "system", "content": "S" * 20_000},
        {"role": "assistant", "content": prior},
        {"role": "user", "content": "hello"},
    ]
    compacted, _diag = compact_upstream_messages_for_budget(messages, _TINY_BUDGET)
    assert compacted[1]["content"] == prior


def test_compact_still_shortens_huge_prior_assistant() -> None:
    huge = "old assistant chatter " * 4000
    messages = [
        {"role": "system", "content": "system"},
        {"role": "assistant", "content": huge},
        {"role": "user", "content": "hello"},
    ]
    compacted, diag = compact_upstream_messages_for_budget(messages, _TINY_BUDGET)
    assert len(compacted[1]["content"]) < len(huge)
    assert "upstream budget" in compacted[1]["content"]
    assert diag.get("compacted") is True
