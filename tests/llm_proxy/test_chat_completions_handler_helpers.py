from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from llm_proxy.chat_completions_handler_helpers import (
    append_pipeline_step_trace,
    build_forced_think_value,
    load_proxy_settings_and_model,
    rag_request_completed_payload,
    web_supplement_used_from_trace,
)


def test_build_forced_think_value_respects_body_override() -> None:
    assert (
        build_forced_think_value(
            body={"think": False},
            active_build={"chat_think": True},
            model_name="llama3",
        )
        is None
    )


def test_build_forced_think_value_non_gpt_oss_maps_chat_think_bool() -> None:
    assert (
        build_forced_think_value(
            body={},
            active_build={"chat_think": True},
            model_name="llama3",
        )
        is True
    )
    assert (
        build_forced_think_value(
            body={},
            active_build={"chat_think": False},
            model_name="llama3",
        )
        is False
    )


def test_build_forced_think_value_gpt_oss_uses_reasoning_level() -> None:
    assert (
        build_forced_think_value(
            body={"reasoning_level": "high"},
            active_build={"chat_think": True},
            model_name="gpt-oss-20b",
        )
        == "high"
    )
    assert (
        build_forced_think_value(
            body={},
            active_build={"chat_think": True},
            model_name="gpt-oss-20b",
        )
        == "medium"
    )


def test_append_pipeline_step_trace_appends_meta() -> None:
    trace: dict[str, Any] = {}
    append_pipeline_step_trace(trace, step_id="rag_retrieve", status="ok", reason="done")
    steps = trace.get("pipeline_steps") or []
    assert len(steps) == 1
    assert steps[0]["id"] == "rag_retrieve"
    assert steps[0]["status"] == "ok"
    assert steps[0]["reason"] == "done"


def test_web_supplement_used_from_trace() -> None:
    assert web_supplement_used_from_trace({}) is False
    assert web_supplement_used_from_trace({"internet": {"used": True}}) is True
    assert web_supplement_used_from_trace({"internet": {"web_supplement": {"used": True}}}) is True


def test_load_proxy_settings_and_model_falls_back_to_proxy_settings_model() -> None:
    class Repo:
        def get_app_setting(self, key: str) -> str | None:
            if key == "proxy_settings":
                return json.dumps({"model": "from-settings"})
            return None

    settings, model = load_proxy_settings_and_model(lambda: Repo())
    assert model == "from-settings"
    assert isinstance(settings, dict)


def test_rag_request_completed_payload_includes_web_supplement_flag() -> None:
    ctx = SimpleNamespace(chunks_info=[{"id": 1}], max_score=0.9, rag_quality=None, coverage_report=None)
    payload = rag_request_completed_payload(
        user_query="hello",
        trace_id="t1",
        use_model="m",
        requested_model="m",
        latency_ms=10,
        prompt_tokens=1,
        completion_tokens=2,
        rag_context_for_obs=ctx,
        rag_timings={"embed": 1.0},
        trace={"internet": {"used": True}},
        stream=False,
        is_autocomplete=False,
    )
    assert payload["event"] == "rag_request_completed"
    assert payload["chunks_count"] == 1
    assert payload["web_supplement_used"] is True
    assert payload["rag_steps"] == {"embed": 1.0}
