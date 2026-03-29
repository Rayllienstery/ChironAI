"""OpenAI legacy ``text_completion`` JSON and SSE lines (shared by chat bridge and /v1/completions)."""

from __future__ import annotations

import json
import time
import uuid
from typing import Any


def non_stream_text_completion_response(
    *,
    use_model: str,
    text: str,
    finish_reason: str | None,
    prompt_tokens_approx: int,
    completion_tokens_approx: int,
) -> dict[str, Any]:
    _pt = max(0, int(prompt_tokens_approx))
    _ct = max(0, int(completion_tokens_approx))
    return {
        "id": f"cmpl-{uuid.uuid4().hex[:24]}",
        "object": "text_completion",
        "created": int(time.time()),
        "model": use_model,
        "choices": [
            {
                "text": text if text else "",
                "index": 0,
                "logprobs": None,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": _pt,
            "completion_tokens": _ct,
            "total_tokens": _pt + _ct,
        },
    }


def legacy_completions_stream_line(
    oid: str,
    model: str,
    text_delta: str,
    finish_reason: str | None,
) -> str:
    payload = {
        "id": oid,
        "object": "text_completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "text": text_delta,
                "index": 0,
                "logprobs": None,
                "finish_reason": finish_reason,
            }
        ],
    }
    return f"data: {json.dumps(payload)}\n\n"


__all__ = ["legacy_completions_stream_line", "non_stream_text_completion_response"]
