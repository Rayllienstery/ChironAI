"""LLM Proxy build presets: storage, OpenAI /v1/models entries, merge into proxy settings."""

from __future__ import annotations

import json
import re
from typing import Any

LLM_PROXY_BUILDS_APP_KEY = "llm_proxy_builds"

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
    if backend not in ("dumb", "claw"):
        errors.append("backend must be 'dumb' or 'claw'")

    ollama_model = str(build.get("ollama_model") or "").strip()
    if backend in ("dumb", "claw") and not ollama_model:
        errors.append("dumb and claw builds require ollama_model")

    prompt_name = str(build.get("prompt_name") or "").strip()
    if not prompt_name:
        errors.append("prompt_name is required")

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
        "ollama_model": ollama_model,
        "prompt_name": prompt_name,
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
        "private": bool(build.get("private", False)),
        "rag_collection": str(build.get("rag_collection") or "").strip(),
    }

    t = build.get("temperature")
    if t is not None and str(t).strip() != "":
        try:
            out["temperature"] = float(t)
        except (TypeError, ValueError):
            pass
    tp = build.get("top_p")
    if tp is not None and str(tp).strip() != "":
        try:
            out["top_p"] = float(tp)
        except (TypeError, ValueError):
            pass

    ms = build.get("max_agent_steps")
    if ms is not None and str(ms).strip() != "":
        try:
            out["max_agent_steps"] = int(ms)
        except (TypeError, ValueError):
            pass

    nc = build.get("num_ctx")
    if nc is not None and str(nc).strip() != "":
        try:
            out["num_ctx"] = int(nc)
        except (TypeError, ValueError):
            pass

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


def openai_model_objects_for_builds(builds: list[dict[str, Any]]) -> list[dict[str, object]]:
    """OpenAI GET /v1/models `data[]` entries (stable order: by id)."""
    sorted_b = sorted(builds, key=lambda x: str(x.get("id") or "").lower())
    return [
        {
            "id": str(b["id"]),
            "object": "model",
            "created": 0,
            "owned_by": "local",
        }
        for b in sorted_b
    ]


def merge_build_into_proxy_settings(
    base: dict[str, Any], build: dict[str, Any]
) -> dict[str, Any]:
    """Overlay build fields onto proxy_settings dict for dumb pipeline."""
    out = dict(base)
    keys_copy = (
        "prompt_name",
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
    """Extra Ollama `options` keys from build (e.g. num_ctx)."""
    opts: dict[str, Any] = {}
    nc = build.get("num_ctx")
    if nc is not None:
        try:
            n = int(nc)
            if n >= 256:
                opts["num_ctx"] = n
        except (TypeError, ValueError):
            pass
    return opts


def diagnose_build(
    build: dict[str, Any],
    *,
    ollama_tag_names: set[str],
    prompt_exists: bool,
    qdrant_collection_names: set[str] | None = None,
    claw_reachable: bool | None = None,
) -> tuple[list[str], bool]:
    """Return (issues, healthy) for WebUI list/detail."""
    issues: list[str] = []
    backend = str(build.get("backend") or "dumb").strip().lower()
    om = str(build.get("ollama_model") or "").strip()
    if backend in ("dumb", "claw"):
        if om and ollama_tag_names and om not in ollama_tag_names:
            issues.append(f'Ollama model "{om}" is not in the current tag list (removed or renamed?)')
    pn = str(build.get("prompt_name") or "").strip()
    if pn and not prompt_exists:
        issues.append(f'Prompt template "{pn}" not found under prompts/')
    rc = str(build.get("rag_collection") or "").strip()
    if rc and qdrant_collection_names is not None and rc not in qdrant_collection_names:
        issues.append(f'RAG collection "{rc}" not found in Qdrant')
    if backend == "claw":
        if claw_reachable is False:
            issues.append("ClawCode OpenAI endpoint is not reachable")
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
