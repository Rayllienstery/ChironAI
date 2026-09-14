"""Compact host status for iPhone Shortcuts (SSH curl to localhost)."""

from __future__ import annotations

from typing import Any

DEFAULT_GPU_BUSY_PCT = 15


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _nonempty(value: Any) -> str:
    text = str(value or "").strip()
    return text


def _trace_model(trace: dict[str, Any]) -> str:
    request = _as_dict(trace.get("request"))
    provider = _as_dict(trace.get("provider") or trace.get("ollama"))
    for candidate in (provider.get("model"), request.get("actual_model"), request.get("requested_model")):
        label = _nonempty(candidate)
        if label:
            return label
    return ""


def _trace_tokens(trace: dict[str, Any]) -> int | None:
    provider = _as_dict(trace.get("provider") or trace.get("ollama"))
    estimates = _as_dict(provider.get("tokens_estimates"))
    for key in ("completion_tokens_estimated", "total_tokens_estimated"):
        raw = estimates.get(key)
        try:
            number = int(raw)
        except (TypeError, ValueError):
            continue
        if number >= 0:
            return number
    return None


def _detail_from_traces(traces: list[dict[str, Any]]) -> str | None:
    if not traces:
        return None
    first = traces[0] if isinstance(traces[0], dict) else {}
    model = _trace_model(first)
    tokens = _trace_tokens(first)
    extra = f" +{len(traces) - 1}" if len(traces) > 1 else ""
    if model and tokens is not None:
        return f"{model} · {tokens} tok{extra}"
    if model:
        return f"{model}{extra}"
    if tokens is not None:
        return f"{tokens} tok{extra}"
    return f"{len(traces)} live" if traces else None


def _human_message(
    *,
    generating: bool,
    kind: str | None,
    detail: str | None,
    gpu_pct: int | None,
) -> str:
    if generating and kind == "gpu":
        pct = f"{gpu_pct}%" if gpu_pct is not None else "busy"
        return f"Generating (GPU {pct})"
    if generating:
        return f"Generating{f': {detail}' if detail else ''}"
    return "PC awake, Chiron idle"


def build_phone_host_status(
    traces: list[Any] | None,
    gpu: dict[str, Any] | None,
    *,
    proxy_status: str | None = None,
    gpu_busy_pct: int = DEFAULT_GPU_BUSY_PCT,
) -> dict[str, Any]:
    """Aggregate live proxy traces and GPU util into a Shortcut-sized payload."""

    rows = [row for row in (traces or []) if isinstance(row, dict)]
    gpu_slice = gpu if isinstance(gpu, dict) else None
    raw_gpu = None if gpu_slice is None else gpu_slice.get("utilization_pct")
    try:
        gpu_pct = int(raw_gpu) if raw_gpu is not None else None
    except (TypeError, ValueError):
        gpu_pct = None
    threshold = max(0, int(gpu_busy_pct))
    llm_busy = bool(rows)
    gpu_busy = gpu_pct is not None and gpu_pct >= threshold
    generating = llm_busy or gpu_busy
    kind: str | None
    if llm_busy:
        kind = "llm"
    elif gpu_busy:
        kind = "gpu"
    else:
        kind = None
    detail = _detail_from_traces(rows)
    if kind == "gpu" and detail is None and gpu_pct is not None:
        detail = f"GPU {gpu_pct}%"
    status_label = _nonempty(proxy_status) or ("Response" if llm_busy else "Idle")
    return {
        "host": "awake",
        "chiron": "up",
        "generating": generating,
        "kind": kind,
        "detail": detail,
        "gpu_pct": gpu_pct,
        "active_traces": len(rows),
        "status": status_label,
        "message": _human_message(generating=generating, kind=kind, detail=detail, gpu_pct=gpu_pct),
    }
