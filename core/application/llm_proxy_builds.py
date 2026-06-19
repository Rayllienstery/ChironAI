"""LLM Proxy build presets: storage, OpenAI /v1/models entries, merge into proxy settings."""

from __future__ import annotations

import contextlib
import json
import re
from typing import Any

LLM_PROXY_BUILDS_APP_KEY = "llm_proxy_builds"
DEFAULT_NUM_PREDICT = 65536
MAX_NUM_PREDICT = 262144

_ID_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$")


def load_builds_json(raw: str | None) -> list[dict[str, Any]]:
    if not raw or not str(raw).strip():
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    out: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            out.append(dict(item))
    return out


def dump_builds_json(builds: list[dict[str, Any]]) -> str:
    return json.dumps(builds, ensure_ascii=False)


def validate_build_id(build_id: str) -> str | None:
    s = (build_id or "").strip()
    if not s or not _ID_RE.match(s):
        return "Build id must start with a letter and contain only letters, digits, ._- (max 128 chars)"
    return None


def normalize_build(build: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
    """Return (normalized_build, errors)."""
    errors: list[str] = []
    bid = str(build.get("id") or "").strip()
    err = validate_build_id(bid)
    if err:
        errors.append(err)
        return None, errors

    backend = str(build.get("backend") or "dumb").strip().lower()
    if backend not in ("dumb", "rag_fusion"):
        errors.append("backend must be 'rag_fusion'")

    provider_id = str(build.get("provider_id") or "").strip()
    model = str(build.get("model") or "").strip()
    legacy_ollama_model = str(build.get("ollama_model") or "").strip()
    if not provider_id and legacy_ollama_model:
        provider_id = "ollama"
    if not model and legacy_ollama_model:
        model = legacy_ollama_model
    if backend in ("dumb", "rag_fusion") and not provider_id:
        errors.append("rag_fusion builds require provider_id")
    if backend in ("dumb", "rag_fusion") and not model:
        errors.append("rag_fusion builds require model")

    use_prompt_template = build.get("use_prompt_template", True) is not False
    prompt_name = str(build.get("prompt_name") or "").strip()
    if use_prompt_template and not prompt_name:
        errors.append("prompt_name is required when use_prompt_template is enabled")

    max_steps = build.get("max_agent_steps")
    if max_steps is not None and str(max_steps).strip() != "":
        try:
            n = int(max_steps)
            if n < 1 or n > 256:
                errors.append("max_agent_steps must be 1–256 or empty")
        except (TypeError, ValueError):
            errors.append("max_agent_steps must be an integer")

    for key in ("temperature", "top_p"):
        v = build.get(key)
        if v is None or (isinstance(v, str) and not v.strip()):
            continue
        try:
            float(v)
        except (TypeError, ValueError):
            errors.append(f"{key} must be a number or empty")

    num_ctx = build.get("num_ctx")
    if num_ctx is not None and str(num_ctx).strip() != "":
        try:
            nc = int(num_ctx)
            if nc < 256:
                errors.append("num_ctx must be >= 256 or empty")
        except (TypeError, ValueError):
            errors.append("num_ctx must be a positive integer or empty")

    num_predict = build.get("num_predict")
    if num_predict is not None and str(num_predict).strip() != "":
        try:
            np = int(num_predict)
            if np < 1 or np > MAX_NUM_PREDICT:
                errors.append(f"num_predict must be between 1 and {MAX_NUM_PREDICT} or empty")
        except (TypeError, ValueError):
            errors.append("num_predict must be an integer or empty")

    def _optional_bounded_int(field: str, raw: Any, lo: int, hi: int) -> None:
        if raw is None or (isinstance(raw, str) and not str(raw).strip()):
            return
        try:
            n = int(raw)
            if n < lo or n > hi:
                errors.append(f"{field} must be between {lo} and {hi} or empty")
        except (TypeError, ValueError):
            errors.append(f"{field} must be an integer or empty")

    _optional_bounded_int("context_chunk_chars", build.get("context_chunk_chars"), 64, 500_000)
    _optional_bounded_int("context_total_chars", build.get("context_total_chars"), 256, 2_000_000)
    _optional_bounded_int("rag_top_k", build.get("rag_top_k"), 1, 256)

    if errors:
        return None, errors

    out: dict[str, Any] = {
        "id": bid,
        "display_name": str(build.get("display_name") or bid).strip() or bid,
        "backend": backend,
        "provider_id": provider_id,
        "model": model,
        "vision_model": str(build.get("vision_model") or "").strip(),
        "prompt_name": prompt_name,
        "use_prompt_template": use_prompt_template,
        "rag_enabled": bool(build.get("rag_enabled", True)),
        "skills_enabled": bool(build.get("skills_enabled", True)),
        "web_enabled": bool(build.get("web_enabled", True)),
        "fetch_web_knowledge": bool(build.get("fetch_web_knowledge", False)),
        "web_interaction_enabled": bool(build.get("web_interaction_enabled", False)),
        "web_interaction_on_keywords": build.get("web_interaction_on_keywords", True) is not False,
        "web_interaction_on_low_confidence_framework": build.get(
            "web_interaction_on_low_confidence_framework", True
        )
        is not False,
        "web_interaction_ddg_news": bool(build.get("web_interaction_ddg_news", False)),
        "web_interaction_fetch_page": bool(build.get("web_interaction_fetch_page", False)),
        "web_interaction_wikipedia": bool(build.get("web_interaction_wikipedia", False)),
        "code_only": bool(build.get("code_only", False)),
        "include_rag_metadata": bool(build.get("include_rag_metadata", True)),
        "reasoning_level": str(build.get("reasoning_level") or "").strip(),
        "chat_think": bool(build.get("chat_think", False)),
        "ide_mode": bool(build.get("ide_mode", False)),
        "private": bool(build.get("private", False)),
        "rag_collection": str(build.get("rag_collection") or "").strip(),
        # When False: client may still send stream=true; proxy calls Ollama once (non-stream)
        # and emits a single OpenAI-shaped SSE burst (role + content/tool_calls + finish + [DONE]).
        "sse_streaming": build.get("sse_streaming", True) is not False,
    }

    t = build.get("temperature")
    if t is not None and str(t).strip() != "":
        with contextlib.suppress(TypeError, ValueError):
            out["temperature"] = float(t)
    tp = build.get("top_p")
    if tp is not None and str(tp).strip() != "":
        with contextlib.suppress(TypeError, ValueError):
            out["top_p"] = float(tp)

    ms = build.get("max_agent_steps")
    if ms is not None and str(ms).strip() != "":
        with contextlib.suppress(TypeError, ValueError):
            out["max_agent_steps"] = int(ms)

    nc = build.get("num_ctx")
    if nc is not None and str(nc).strip() != "":
        with contextlib.suppress(TypeError, ValueError):
            out["num_ctx"] = int(nc)

    np = build.get("num_predict")
    if np is None or str(np).strip() == "":
        out["num_predict"] = DEFAULT_NUM_PREDICT
    else:
        try:
            out["num_predict"] = int(np)
        except (TypeError, ValueError):
            out["num_predict"] = DEFAULT_NUM_PREDICT

    for lim_key, lo, hi in (
        ("context_chunk_chars", 64, 500_000),
        ("context_total_chars", 256, 2_000_000),
        ("rag_top_k", 1, 256),
    ):
        lv = build.get(lim_key)
        if lv is not None and str(lv).strip() != "":
            try:
                n = int(lv)
                if lo <= n <= hi:
                    out[lim_key] = n
            except (TypeError, ValueError):
                pass

    if not out["web_enabled"]:
        out["fetch_web_knowledge"] = False
        out["web_interaction_enabled"] = False

    return out, []


def validate_builds_list(builds: list[dict[str, Any]]) -> tuple[list[dict[str, Any]] | None, list[str]]:
    seen: set[str] = set()
    normalized: list[dict[str, Any]] = []
    all_errs: list[str] = []
    for i, b in enumerate(builds):
        nb, errs = normalize_build(b)
        if errs:
            all_errs.append(f"Build #{i + 1}: " + "; ".join(errs))
            continue
        assert nb is not None
        if nb["id"] in seen:
            all_errs.append(f"Duplicate build id: {nb['id']}")
            continue
        seen.add(nb["id"])
        normalized.append(nb)
    if all_errs:
        return None, all_errs
    return normalized, []


def find_build_by_id(builds: list[dict[str, Any]], model_id: str) -> dict[str, Any] | None:
    key = (model_id or "").strip()
    if not key:
        return None
    for b in builds:
        if str(b.get("id") or "").strip() == key:
            return b
    return None


def openai_client_capability_fields() -> dict[str, object]:
    """Extra model fields consumed by OpenAI-compatible clients with models.dev-style gates."""
    return {
        # Chiron extension / legacy client field.
        "supports_vision": True,
        # Common Cline/Roo/Kilo-style aliases. Some clients gate image
        # attachment before sending the request and only inspect one of these.
        "supportsImages": True,
        "supports_images": True,
        # OpenCode/models.dev fields. Without modalities.input including "image",
        # OpenCode treats custom OpenAI-compatible models as text-only.
        "attachment": True,
        "input_modalities": ["text", "image"],
        "output_modalities": ["text"],
        "modalities": {"input": ["text", "image"], "output": ["text"]},
        "capabilities": ["completion", "tools", "vision"],
        "supportsTools": True,
        "supports_tools": True,
        "tool_call": True,
    }


def openai_model_objects_for_builds(builds: list[dict[str, Any]]) -> list[dict[str, object]]:
    """OpenAI GET /v1/models `data[]` entries (stable order: by id)."""
    sorted_b = sorted(builds, key=lambda x: str(x.get("id") or "").lower())
    rows: list[dict[str, object]] = []
    for b in sorted_b:
        upstream_model = str(b.get("model") or b.get("ollama_model") or "").strip()
        metadata: dict[str, object] = {"ollama_model": upstream_model} if upstream_model else {}
        context_length = None
        try:
            raw_ctx = b.get("num_ctx")
            if raw_ctx is not None and str(raw_ctx).strip() != "":
                ctx = int(raw_ctx)
                if ctx >= 256:
                    context_length = ctx
        except (TypeError, ValueError):
            context_length = None
        if context_length is not None:
            metadata["context_length"] = context_length
            metadata["num_ctx"] = context_length
        row: dict[str, object] = {
            "id": str(b["id"]),
            "object": "model",
            "created": 0,
            "owned_by": "local",
        }
        row.update(openai_client_capability_fields())
        if context_length is not None:
            row["context_length"] = context_length
            row["num_ctx"] = context_length
        row["metadata"] = metadata
        rows.append(row)
    return rows


def merge_build_into_proxy_settings(
    base: dict[str, Any], build: dict[str, Any]
) -> dict[str, Any]:
    """Overlay build fields onto proxy_settings dict for dumb pipeline."""
    out = dict(base)
    keys_copy = (
        "prompt_name",
        "use_prompt_template",
        "fetch_web_knowledge",
        "web_interaction_enabled",
        "web_interaction_on_keywords",
        "web_interaction_on_low_confidence_framework",
        "web_interaction_ddg_news",
        "web_interaction_fetch_page",
        "web_interaction_wikipedia",
        "code_only",
        "include_rag_metadata",
        "rag_collection",
        "num_predict",
        "context_chunk_chars",
        "context_total_chars",
        "rag_top_k",
    )
    for k in keys_copy:
        if k in build:
            out[k] = build[k]

    if "temperature" in build:
        out["temperature"] = build["temperature"]
    if "top_p" in build:
        out["top_p"] = build["top_p"]
    out["rag_enabled"] = bool(build.get("rag_enabled", True))
    return out


def build_ollama_options(build: dict[str, Any]) -> dict[str, Any]:
    """Extra Ollama `options` keys from build (e.g. num_ctx, num_predict)."""
    opts: dict[str, Any] = {}
    nc = build.get("num_ctx")
    if nc is not None:
        try:
            n = int(nc)
            if n >= 256:
                opts["num_ctx"] = n
        except (TypeError, ValueError):
            pass
    np = build.get("num_predict", DEFAULT_NUM_PREDICT)
    try:
        n = int(np)
        if 1 <= n <= MAX_NUM_PREDICT:
            opts["num_predict"] = n
        else:
            opts["num_predict"] = DEFAULT_NUM_PREDICT
    except (TypeError, ValueError):
        opts["num_predict"] = DEFAULT_NUM_PREDICT
    return opts


def diagnose_build(
    build: dict[str, Any],
    *,
    ollama_tag_names: set[str],
    prompt_exists: bool,
    qdrant_collection_names: set[str] | None = None,
) -> tuple[list[str], bool]:
    """Return (issues, healthy) for WebUI list/detail."""
    issues: list[str] = []
    provider_id = str(build.get("provider_id") or "").strip() or ("ollama" if str(build.get("ollama_model") or "").strip() else "")
    model = str(build.get("model") or "").strip() or str(build.get("ollama_model") or "").strip()
    if provider_id == "ollama" and model and ollama_tag_names and model not in ollama_tag_names:
        issues.append(f'Ollama model "{model}" is not in the current tag list (removed or renamed?)')
    use_prompt_template = build.get("use_prompt_template", True) is not False
    pn = str(build.get("prompt_name") or "").strip()
    if use_prompt_template and pn and not prompt_exists:
        issues.append(f'Prompt template "{pn}" not found in the prompt store')
    rc = str(build.get("rag_collection") or "").strip()
    if rc and qdrant_collection_names is not None and rc not in qdrant_collection_names:
        issues.append(f'RAG collection "{rc}" not found in Qdrant')
    return issues, len(issues) == 0


def extract_context_length_from_show(details: dict[str, Any] | None) -> int | None:
    """Best-effort context length from Ollama POST /api/show JSON."""
    if not details or not isinstance(details, dict):
        return None
    mi = details.get("model_info")
    if isinstance(mi, dict):
        for k, v in mi.items():
            lk = str(k).lower()
            if "context_length" in lk and isinstance(v, (int, float)):
                return int(v)
    # top-level fallbacks seen in some Ollama versions
    for k in ("context_length", "num_ctx"):
        v = details.get(k)
        if isinstance(v, (int, float)):
            return int(v)
    return None
