"""Web supplement step for LLM proxy pipeline."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class WebSupplementStepMeta:
    id: str = "web_supplement"
    icon: str = "travel_explore"
    title: str = "Web supplement"
    description: str = "Fetch DuckDuckGo/Wikipedia supplement when policy and triggers allow."


@dataclass
class WebSupplementStepResult:
    text: str | None
    meta: dict[str, Any]
    status: str
    reason: str | None = None


def run_web_supplement_step(
    *,
    w: Any,
    is_autocomplete: bool,
    doc_refactor_skip: bool,
    last_user: str,
    rag_ctx_for_log: Any | None,
    effective_confidence_threshold: float,
    proxy_settings: dict[str, Any],
) -> WebSupplementStepResult:
    default_meta: dict[str, Any] = {
        "trigger": "none",
        "used": False,
        "error": None,
        "duration_ms": 0,
        "snippets_chars": 0,
    }
    if is_autocomplete:
        return WebSupplementStepResult(text=None, meta=default_meta, status="disabled", reason="autocomplete")

    _bf = getattr(w, "build_web_supplement_for_proxy", None)
    if not callable(_bf):
        return WebSupplementStepResult(text=None, meta=default_meta, status="disabled", reason="builder_unavailable")

    if doc_refactor_skip:
        meta = {
            **default_meta,
            "skip_reason": "workspace_doc_refactor",
            "duration_ms": 0,
        }
        return WebSupplementStepResult(text=None, meta=meta, status="disabled", reason="workspace_doc_refactor")

    try:
        _tws = time.time()
        _mx = float(rag_ctx_for_log.max_score) if rag_ctx_for_log is not None else 0.0
        ps: dict[str, Any] = {str(k): v for k, v in (proxy_settings or {}).items()}
        web_supplement_text, web_sup_meta = _bf(
            last_user or "",
            _mx,
            float(effective_confidence_threshold),
            ps,
        )
        web_sup_meta = {
            **(web_sup_meta or {}),
            "duration_ms": int((time.time() - _tws) * 1000),
        }
        status = "executed" if web_supplement_text else "disabled"
        reason = None if web_supplement_text else "no_supplement"
        return WebSupplementStepResult(
            text=web_supplement_text,
            meta=web_sup_meta,
            status=status,
            reason=reason,
        )
    except Exception as exc:
        meta = {**default_meta, "error": str(exc)}
        return WebSupplementStepResult(text=None, meta=meta, status="failed", reason="exception")


__all__ = ["WebSupplementStepMeta", "WebSupplementStepResult", "run_web_supplement_step"]
