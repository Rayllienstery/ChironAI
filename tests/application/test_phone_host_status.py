from __future__ import annotations

from application.phone_host_status import build_phone_host_status


def test_status_skips_null_and_invalid_token_estimates() -> None:
    traces = [
        {
            "request": {"requested_model": "llama"},
            "provider": {"tokens_estimates": {"completion_tokens_estimated": None, "total_tokens_estimated": "nope"}},
        }
    ]
    payload = build_phone_host_status(traces, None, proxy_status="Response")
    assert payload["generating"] is True
    assert payload["kind"] == "llm"
    assert payload["detail"] == "llama"
    assert payload["gpu_pct"] is None


def test_status_uses_valid_token_count() -> None:
    traces = [
        {
            "request": {},
            "provider": {"tokens_estimates": {"completion_tokens_estimated": 12}},
        }
    ]
    payload = build_phone_host_status(traces, {"utilization_pct": "bad"})
    assert payload["detail"] == "12 tok"
    assert "Generating" in payload["message"]
