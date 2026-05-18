"""Gemini tool state, native tools preflight, and shell tool sanitization."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any

from llm_proxy.contracts import LlmProxyWiring
from llm_proxy.ollama_compat import is_gemini_family_model_name


def _sanitize_tool_name(raw: object, *, fallback: str = "tool") -> str:
    if isinstance(raw, str):
        name = raw.strip()
        if name:
            return name
    return fallback


def _message_tool_call_id(message: dict[str, Any]) -> str:
    for key in ("tool_call_id", "tool_callid", "call_id", "id"):
        value = message.get(key)
        if isinstance(value, str):
            value = value.strip()
            if value:
                return value
    return ""


_THOUGHT_SIGNATURE_SKIP_VALIDATOR = "skip_thought_signature_validator"
_GEMINI_TOOL_STATE_TTL_SECONDS = 7 * 24 * 60 * 60
_GEMINI_TOOL_STATE_SCHEMA_INIT_LOCK = threading.Lock()
_GEMINI_TOOL_STATE_SCHEMA_INIT_PATHS: set[str] = set()


def _is_gemini_model_name(model_name: str | None) -> bool:
    return is_gemini_family_model_name(model_name)


def _resolve_default_webui_db_path() -> str:
    env_path = os.getenv("WEBUI_DB_PATH")
    if env_path:
        return env_path
    project_root = Path(__file__).resolve().parents[3]
    return str(project_root / "logs" / "webui.db")


def _resolve_proxy_db_path_from_wiring(w: LlmProxyWiring | None) -> str:
    if w is not None:
        try:
            repo = w.get_logs_repository()
            path = getattr(repo, "db_path", None)
            if path:
                return str(path)
        except Exception:
            pass
    return _resolve_default_webui_db_path()


def _ensure_gemini_tool_state_schema(db_path: str) -> None:
    p = str(db_path or "").strip()
    if not p:
        return
    with _GEMINI_TOOL_STATE_SCHEMA_INIT_LOCK:
        if p in _GEMINI_TOOL_STATE_SCHEMA_INIT_PATHS:
            return
    try:
        Path(p).parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(p) as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS gemini_tool_call_state (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    call_id TEXT NOT NULL,
                    model TEXT NOT NULL,
                    function_name TEXT,
                    thought_signature TEXT,
                    trace_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(call_id, model)
                );
                CREATE INDEX IF NOT EXISTS idx_gemini_tool_call_state_call_id
                    ON gemini_tool_call_state(call_id);
                CREATE INDEX IF NOT EXISTS idx_gemini_tool_call_state_updated_at
                    ON gemini_tool_call_state(updated_at);
                """
            )
            conn.commit()
    except Exception:
        return
    with _GEMINI_TOOL_STATE_SCHEMA_INIT_LOCK:
        _GEMINI_TOOL_STATE_SCHEMA_INIT_PATHS.add(p)


def _gemini_tool_state_lookup(
    db_path: str | None,
    *,
    call_id: str,
    model_name: str | None,
) -> dict[str, str]:
    cid = str(call_id or "").strip()
    path = str(db_path or "").strip()
    if not cid or not path:
        return {}
    _ensure_gemini_tool_state_schema(path)
    model = str(model_name or "").strip()
    try:
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            row = None
            if model:
                row = conn.execute(
                    """
                    SELECT function_name, thought_signature
                    FROM gemini_tool_call_state
                    WHERE call_id = ? AND model = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (cid, model),
                ).fetchone()
            if row is None:
                row = conn.execute(
                    """
                    SELECT function_name, thought_signature
                    FROM gemini_tool_call_state
                    WHERE call_id = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (cid,),
                ).fetchone()
            if row is None:
                return {}
            out: dict[str, str] = {}
            fn = row["function_name"]
            sig = row["thought_signature"]
            if isinstance(fn, str) and fn.strip():
                out["function_name"] = fn.strip()
            if isinstance(sig, str) and sig.strip():
                out["thought_signature"] = sig.strip()
            return out
    except Exception:
        return {}


def _gemini_tool_state_upsert_many(
    db_path: str | None,
    *,
    rows: list[dict[str, str]],
    ttl_seconds: int = _GEMINI_TOOL_STATE_TTL_SECONDS,
) -> int:
    path = str(db_path or "").strip()
    if not path or not rows:
        return 0
    _ensure_gemini_tool_state_schema(path)
    payload: list[tuple[str, str, str, str, str]] = []
    for row in rows:
        call_id = str(row.get("call_id") or "").strip()
        model = str(row.get("model") or "").strip()
        if not call_id or not model:
            continue
        payload.append(
            (
                call_id,
                model,
                str(row.get("function_name") or "").strip(),
                str(row.get("thought_signature") or "").strip(),
                str(row.get("trace_id") or "").strip(),
            )
        )
    if not payload:
        return 0
    try:
        with sqlite3.connect(path) as conn:
            conn.executemany(
                """
                INSERT INTO gemini_tool_call_state
                    (call_id, model, function_name, thought_signature, trace_id, created_at, updated_at)
                VALUES (?, ?, NULLIF(?, ''), NULLIF(?, ''), NULLIF(?, ''), CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                ON CONFLICT(call_id, model) DO UPDATE SET
                    function_name = COALESCE(excluded.function_name, gemini_tool_call_state.function_name),
                    thought_signature = COALESCE(excluded.thought_signature, gemini_tool_call_state.thought_signature),
                    trace_id = COALESCE(excluded.trace_id, gemini_tool_call_state.trace_id),
                    updated_at = CURRENT_TIMESTAMP
                """,
                payload,
            )
            ttl = max(int(ttl_seconds or 0), 60)
            conn.execute(
                "DELETE FROM gemini_tool_call_state WHERE updated_at < datetime('now', ?)",
                (f"-{ttl} seconds",),
            )
            conn.commit()
    except Exception:
        return 0
    return len(payload)


def _build_tool_call_id_to_name(messages: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in messages:
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        tool_calls = m.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for c in tool_calls:
            if not isinstance(c, dict):
                continue
            call_id = _message_tool_call_id(c)
            fn = c.get("function") if isinstance(c.get("function"), dict) else {}
            name = _sanitize_tool_name(fn.get("name") if isinstance(fn, dict) else None, fallback="")
            if call_id and name:
                out[call_id] = name
    return out


def _build_tool_call_id_to_signature(messages: list[Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for m in messages:
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        tool_calls = m.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for c in tool_calls:
            if not isinstance(c, dict):
                continue
            call_id = _message_tool_call_id(c)
            if not call_id:
                continue
            fn = c.get("function") if isinstance(c.get("function"), dict) else {}
            sig = _extract_tool_call_thought_signature(c, fn if isinstance(fn, dict) else {})
            if sig:
                out[call_id] = sig
    return out


def _preflight_native_tool_messages(
    messages: list[Any],
    *,
    model_name: str | None = None,
    trace_id: str | None = None,
    db_path: str | None = None,
) -> tuple[list[Any], dict[str, Any]]:
    tool_call_id_to_name = _build_tool_call_id_to_name(messages)
    tool_call_id_to_signature = _build_tool_call_id_to_signature(messages)
    corrected_indices: list[int] = []
    heuristic_indices: list[int] = []
    heuristic_source_counts: dict[str, int] = {"name_alias": 0, "call_id_map": 0, "fallback": 0}
    is_gemini = _is_gemini_model_name(model_name)
    effective_db_path = str(db_path or "").strip() or _resolve_default_webui_db_path()
    gemini_model = str(model_name or "").strip() or "gemini"
    gemini_signature_recovered_from_db = 0
    gemini_signature_recovered_from_history = 0
    gemini_signature_fallback_sentinel = 0
    gemini_tool_name_recovered_from_db = 0
    gemini_lookup_attempts = 0
    gemini_lookup_hits = 0
    gemini_lookup_cache: dict[str, dict[str, str]] = {}
    assistant_tool_call_fixed_indices: list[int] = []
    rows_to_upsert: list[dict[str, str]] = []
    out: list[Any] = []
    for idx, m in enumerate(messages):
        if not isinstance(m, dict):
            out.append(m)
            continue
        role = m.get("role")
        if role == "assistant":
            tool_calls = m.get("tool_calls")
            if not isinstance(tool_calls, list) or not tool_calls:
                out.append(m)
                continue
            changed = False
            new_calls: list[Any] = []
            for tc in tool_calls:
                if not isinstance(tc, dict):
                    new_calls.append(tc)
                    continue
                tc2 = dict(tc)
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                fn2 = dict(fn) if isinstance(fn, dict) else {}
                call_id = _message_tool_call_id(tc2)
                if call_id:
                    if str(tc2.get("id") or "").strip() != call_id:
                        tc2["id"] = call_id
                        changed = True
                    if str(tc2.get("call_id") or "").strip() != call_id:
                        tc2["call_id"] = call_id
                        changed = True

                fn_name = _sanitize_tool_name(fn2.get("name"), fallback="")
                if not fn_name and call_id:
                    mapped_name = _sanitize_tool_name(tool_call_id_to_name.get(call_id), fallback="")
                    if mapped_name:
                        fn_name = mapped_name
                if not fn_name and is_gemini and call_id:
                    if call_id in gemini_lookup_cache:
                        rec = gemini_lookup_cache[call_id]
                    else:
                        gemini_lookup_attempts += 1
                        rec = _gemini_tool_state_lookup(
                            effective_db_path,
                            call_id=call_id,
                            model_name=gemini_model,
                        )
                        gemini_lookup_cache[call_id] = rec
                        if rec:
                            gemini_lookup_hits += 1
                    rec_name = _sanitize_tool_name(rec.get("function_name"), fallback="")
                    if rec_name:
                        fn_name = rec_name
                        gemini_tool_name_recovered_from_db += 1
                if fn_name and fn2.get("name") != fn_name:
                    fn2["name"] = fn_name
                    changed = True
                if call_id and fn_name:
                    tool_call_id_to_name.setdefault(call_id, fn_name)

                thought_signature = _extract_tool_call_thought_signature(tc2, fn2)
                if not thought_signature and call_id:
                    mapped_sig = str(tool_call_id_to_signature.get(call_id) or "").strip()
                    if mapped_sig:
                        thought_signature = mapped_sig
                        gemini_signature_recovered_from_history += 1
                if not thought_signature and is_gemini and call_id:
                    if call_id in gemini_lookup_cache:
                        rec = gemini_lookup_cache[call_id]
                    else:
                        gemini_lookup_attempts += 1
                        rec = _gemini_tool_state_lookup(
                            effective_db_path,
                            call_id=call_id,
                            model_name=gemini_model,
                        )
                        gemini_lookup_cache[call_id] = rec
                        if rec:
                            gemini_lookup_hits += 1
                    rec_sig = str(rec.get("thought_signature") or "").strip()
                    if rec_sig:
                        thought_signature = rec_sig
                        gemini_signature_recovered_from_db += 1
                if not thought_signature and is_gemini:
                    thought_signature = _THOUGHT_SIGNATURE_SKIP_VALIDATOR
                    gemini_signature_fallback_sentinel += 1
                if thought_signature:
                    if fn2.get("thought_signature") != thought_signature:
                        fn2["thought_signature"] = thought_signature
                        changed = True
                    extra = tc2.get("extra_content")
                    extra_out = dict(extra) if isinstance(extra, dict) else {}
                    google = extra_out.get("google")
                    google_out = dict(google) if isinstance(google, dict) else {}
                    if google_out.get("thought_signature") != thought_signature:
                        google_out["thought_signature"] = thought_signature
                        changed = True
                    extra_out["google"] = google_out
                    tc2["extra_content"] = extra_out
                    if call_id:
                        tool_call_id_to_signature.setdefault(call_id, thought_signature)

                if fn2 != fn:
                    tc2["function"] = fn2
                    changed = True

                if is_gemini and call_id:
                    rows_to_upsert.append(
                        {
                            "call_id": call_id,
                            "model": gemini_model,
                            "function_name": fn_name,
                            "thought_signature": thought_signature,
                            "trace_id": str(trace_id or ""),
                        }
                    )
                new_calls.append(tc2)

            if changed:
                m2 = dict(m)
                m2["tool_calls"] = new_calls
                out.append(m2)
                assistant_tool_call_fixed_indices.append(idx)
            else:
                out.append(m)
            continue

        if role != "tool":
            out.append(m)
            continue
        name = _sanitize_tool_name(m.get("tool_name"), fallback="")
        heuristic_source = ""
        if not name:
            alias_name = _sanitize_tool_name(m.get("name"), fallback="")
            if alias_name:
                name = alias_name
                heuristic_source = "name_alias"
        if not name:
            call_id = _message_tool_call_id(m)
            if call_id:
                mapped_name = _sanitize_tool_name(tool_call_id_to_name.get(call_id), fallback="")
                if mapped_name:
                    name = mapped_name
                    heuristic_source = "call_id_map"
                elif is_gemini:
                    if call_id in gemini_lookup_cache:
                        rec = gemini_lookup_cache[call_id]
                    else:
                        gemini_lookup_attempts += 1
                        rec = _gemini_tool_state_lookup(
                            effective_db_path,
                            call_id=call_id,
                            model_name=gemini_model,
                        )
                        gemini_lookup_cache[call_id] = rec
                        if rec:
                            gemini_lookup_hits += 1
                    rec_name = _sanitize_tool_name(rec.get("function_name"), fallback="")
                    if rec_name:
                        name = rec_name
                        heuristic_source = "call_id_map"
                        gemini_tool_name_recovered_from_db += 1
        if not name:
            name = "tool"
            heuristic_source = "fallback"

        if heuristic_source:
            heuristic_indices.append(idx)
            heuristic_source_counts[heuristic_source] = int(heuristic_source_counts.get(heuristic_source) or 0) + 1

        if m.get("tool_name") != name or m.get("name") != name:
            m2 = dict(m)
            m2["tool_name"] = name
            m2["name"] = name
            out.append(m2)
            corrected_indices.append(idx)
        else:
            out.append(m)
    diag: dict[str, Any] = {}
    if assistant_tool_call_fixed_indices:
        diag["assistant_tool_call_fixes"] = len(assistant_tool_call_fixed_indices)
        diag["assistant_tool_call_fixed_indices"] = assistant_tool_call_fixed_indices[:10]
    if corrected_indices:
        diag["tool_message_name_fixes"] = len(corrected_indices)
        diag["tool_message_name_fixed_indices"] = corrected_indices[:10]
    if heuristic_indices:
        diag["tool_message_name_recovered_heuristic_count"] = len(heuristic_indices)
        diag["tool_message_name_recovered_heuristic_indices"] = heuristic_indices[:10]
        diag["tool_message_name_recovered_heuristic_sources"] = {
            k: v for k, v in heuristic_source_counts.items() if int(v) > 0
        }
    if is_gemini:
        if gemini_lookup_attempts:
            diag["gemini_tool_state_lookup_attempts"] = int(gemini_lookup_attempts)
            diag["gemini_tool_state_lookup_hits"] = int(gemini_lookup_hits)
        if gemini_signature_recovered_from_history:
            diag["gemini_signature_recovered_from_history_count"] = int(
                gemini_signature_recovered_from_history
            )
        if gemini_signature_recovered_from_db:
            diag["gemini_signature_recovered_from_db_count"] = int(gemini_signature_recovered_from_db)
        if gemini_signature_fallback_sentinel:
            diag["gemini_signature_fallback_sentinel_count"] = int(gemini_signature_fallback_sentinel)
        if gemini_tool_name_recovered_from_db:
            diag["gemini_tool_name_recovered_from_db_count"] = int(gemini_tool_name_recovered_from_db)
        if rows_to_upsert:
            upserted = _gemini_tool_state_upsert_many(
                effective_db_path,
                rows=rows_to_upsert,
            )
            if upserted:
                diag["gemini_tool_state_upserted_count"] = int(upserted)
    return out, diag


_GEMINI_SAFE_SCHEMA_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}


def _normalize_schema_for_gemini(raw_schema: Any) -> tuple[dict[str, Any], int]:
    relaxed = 0

    def _norm(node: Any) -> dict[str, Any]:
        nonlocal relaxed
        if not isinstance(node, dict):
            relaxed += 1
            return {"type": "object", "additionalProperties": True}

        out: dict[str, Any] = {}
        node_type = node.get("type")
        if isinstance(node_type, str):
            t = node_type.strip().lower()
            if t in _GEMINI_SAFE_SCHEMA_TYPES:
                out["type"] = t
            elif t:
                relaxed += 1
        elif node_type is not None:
            relaxed += 1

        desc = node.get("description")
        if isinstance(desc, str) and desc.strip():
            out["description"] = desc.strip()
        elif desc is not None:
            relaxed += 1

        enum_raw = node.get("enum")
        if isinstance(enum_raw, list):
            enum_values = [v for v in enum_raw if not isinstance(v, (dict, list))]
            if enum_values:
                out["enum"] = enum_values
            elif enum_raw:
                relaxed += 1
        elif enum_raw is not None:
            relaxed += 1

        object_like = (
            out.get("type") == "object"
            or "properties" in node
            or "required" in node
            or "additionalProperties" in node
        )
        if object_like:
            out.setdefault("type", "object")
            props_in = node.get("properties")
            props_out: dict[str, Any] = {}
            if isinstance(props_in, dict):
                for key, val in props_in.items():
                    if not isinstance(key, str):
                        relaxed += 1
                        continue
                    k = key.strip()
                    if not k:
                        relaxed += 1
                        continue
                    props_out[k] = _norm(val)
            elif props_in is not None:
                relaxed += 1
            out["properties"] = props_out

            required_in = node.get("required")
            if isinstance(required_in, list):
                required_out: list[str] = []
                for raw in required_in:
                    if not isinstance(raw, str):
                        relaxed += 1
                        continue
                    r = raw.strip()
                    if not r:
                        relaxed += 1
                        continue
                    if props_out and r not in props_out:
                        relaxed += 1
                        continue
                    if r not in required_out:
                        required_out.append(r)
                if required_out:
                    out["required"] = required_out
            elif required_in is not None:
                relaxed += 1

            addl = node.get("additionalProperties")
            if isinstance(addl, bool):
                out["additionalProperties"] = addl
            elif isinstance(addl, dict):
                out["additionalProperties"] = _norm(addl)
            elif addl is not None:
                relaxed += 1
            elif not props_out:
                out["additionalProperties"] = True

        array_like = out.get("type") == "array" or "items" in node
        if array_like:
            out.setdefault("type", "array")
            items_in = node.get("items")
            if isinstance(items_in, dict):
                out["items"] = _norm(items_in)
            elif isinstance(items_in, list) and items_in:
                head = items_in[0]
                out["items"] = _norm(head if isinstance(head, dict) else {"type": "object"})
                if len(items_in) > 1:
                    relaxed += len(items_in) - 1
            else:
                out["items"] = {"type": "object", "additionalProperties": True}
                if items_in is not None:
                    relaxed += 1

        if "type" not in out:
            out["type"] = "object"
            out.setdefault("additionalProperties", True)
        return out

    seed = raw_schema if isinstance(raw_schema, dict) else {"type": "object", "additionalProperties": True}
    if raw_schema is not None and not isinstance(raw_schema, dict):
        relaxed += 1
    return _norm(seed), relaxed


def _interpolate_native_tools_for_gemini(
    tools: list[Any],
    *,
    model_name: str | None,
) -> tuple[list[Any], dict[str, Any]]:
    if not _is_gemini_model_name(model_name):
        return tools, {}

    changed = 0
    relaxed_total = 0
    normalized: list[tuple[int, Any]] = []

    for idx, tool in enumerate(tools):
        if not isinstance(tool, dict):
            normalized.append((idx, tool))
            continue
        ttype = str(tool.get("type") or "").strip().lower()
        fn = tool.get("function") if isinstance(tool.get("function"), dict) else {}
        if ttype not in ("", "function") or not isinstance(fn, dict):
            normalized.append((idx, tool))
            continue

        fn_name = _sanitize_tool_name(fn.get("name"), fallback="")
        if not fn_name:
            fn_name = _sanitize_tool_name(tool.get("name"), fallback="")
        if not fn_name:
            normalized.append((idx, tool))
            continue

        fn_out = dict(fn)
        fn_out["name"] = fn_name
        description = str(fn_out.get("description") or tool.get("description") or "").strip()
        if not description:
            description = f"IDE tool `{fn_name}`."
        fn_out["description"] = description

        raw_params = fn_out.get("parameters")
        if not isinstance(raw_params, dict):
            raw_params = tool.get("parameters")
        params_out, relaxed = _normalize_schema_for_gemini(raw_params)
        fn_out["parameters"] = params_out
        relaxed_total += int(relaxed)

        if not isinstance(fn_out.get("strict"), bool):
            fn_out.pop("strict", None)

        tool_out = dict(tool)
        tool_out["type"] = "function"
        tool_out["function"] = fn_out

        if tool_out != tool:
            changed += 1
        normalized.append((idx, tool_out))

    ordered = sorted(
        normalized,
        key=lambda pair: (
            0
            if isinstance(pair[1], dict)
            and isinstance((pair[1].get("function") if isinstance(pair[1].get("function"), dict) else {}), dict)
            and _sanitize_tool_name(
                ((pair[1].get("function") if isinstance(pair[1].get("function"), dict) else {})).get("name"),
                fallback="",
            )
            else 1,
            _sanitize_tool_name(
                (
                    ((pair[1].get("function") if isinstance(pair[1], dict) and isinstance(pair[1].get("function"), dict) else {}))
                    .get("name")
                ),
                fallback="\uffff",
            ).lower(),
            pair[0],
        ),
    )
    out = [item for _, item in ordered]

    diag: dict[str, Any] = {"gemini_tool_interpolation_enabled": True}
    if changed:
        diag["gemini_tool_schema_normalized_count"] = int(changed)
    if relaxed_total:
        diag["gemini_tool_schema_relaxed_count"] = int(relaxed_total)
    if [idx for idx, _ in normalized] != [idx for idx, _ in ordered]:
        diag["gemini_tool_order_stabilized"] = True
    return out, diag


def _preflight_native_tools_payload(tools: list[Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    valid: list[dict[str, Any]] = []
    dropped: list[dict[str, Any]] = []
    for idx, t in enumerate(tools):
        if not isinstance(t, dict):
            dropped.append({"index": idx, "reason": "non_dict"})
            continue
        ttype = str(t.get("type") or "").strip().lower()
        fn = t.get("function") if isinstance(t.get("function"), dict) else {}
        if not isinstance(fn, dict):
            fn = {}
        fn_name = _sanitize_tool_name(fn.get("name"), fallback="")
        if not fn_name:
            fn_name = _sanitize_tool_name(t.get("name"), fallback="")
        if ttype not in ("", "function") or not fn_name:
            dropped.append({"index": idx, "type": ttype or "unknown", "reason": "unsupported_or_missing_name"})
            continue
        fn_out = dict(fn)
        fn_out["name"] = fn_name
        t_out = dict(t)
        t_out["type"] = "function"
        t_out["function"] = fn_out
        valid.append(t_out)
    diag: dict[str, Any] = {}
    if dropped:
        diag["tools_dropped_count"] = len(dropped)
        diag["tools_dropped"] = dropped[:10]
    return valid, diag


def _tool_round_stats_since_last_user(messages: list[Any]) -> dict[str, Any]:
    last_user_idx = -1
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if isinstance(m, dict) and m.get("role") == "user":
            last_user_idx = i
            break
    rounds = 0
    shell_rounds = 0
    non_shell_rounds = 0
    single_tool_rounds = 0
    tool_name_counts: dict[str, int] = {}
    for m in messages[last_user_idx + 1 :]:
        if not isinstance(m, dict) or m.get("role") != "assistant":
            continue
        tool_calls = m.get("tool_calls")
        if not isinstance(tool_calls, list) or not tool_calls:
            continue
        rounds += 1
        names: list[str] = []
        for tc in tool_calls:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            if isinstance(fn, dict):
                names.append(str(fn.get("name") or "").strip().lower())
        if len(names) == 1 and names[0]:
            single_tool_rounds += 1
            tool_name_counts[names[0]] = int(tool_name_counts.get(names[0]) or 0) + 1
        if names and all(n == "shell" for n in names):
            shell_rounds += 1
        else:
            non_shell_rounds += 1
    dominant_tool = ""
    dominant_count = 0
    for name, count in tool_name_counts.items():
        if count > dominant_count:
            dominant_tool = name
            dominant_count = count
    return {
        "rounds": rounds,
        "shell_rounds": shell_rounds,
        "non_shell_rounds": non_shell_rounds,
        "single_tool_rounds": single_tool_rounds,
        "dominant_tool": dominant_tool,
        "dominant_tool_rounds": dominant_count,
    }


_POWERSHELL_COMMAND_WRAPPER_RE = re.compile(
    r"""^\s*(?P<exe>(?:powershell|pwsh)(?:\.exe)?)\s+-Command\s+(?P<q>["'])(?P<script>.*)(?P=q)\s*$""",
    re.IGNORECASE | re.DOTALL,
)




def _looks_like_recursive_get_child_item(cmd: str) -> bool:
    c = cmd.lower()
    return ("get-childitem" in c or "\ngci " in f"\n{c}" or "\ndir " in f"\n{c}" or "\nls " in f"\n{c}") and (
        "-recurse" in c
    )


def _ensure_safe_windows_listing_command(cmd: str) -> str:
    """Avoid hard failures on ACL-protected folders for recursive PowerShell listing."""
    if not isinstance(cmd, str):
        return cmd
    if not _looks_like_recursive_get_child_item(cmd):
        return cmd
    if re.search(r"(?i)-ErrorAction\b", cmd):
        return cmd

    m = _POWERSHELL_COMMAND_WRAPPER_RE.match(cmd)
    if m:
        script = m.group("script")
        if not re.search(r"(?i)-ErrorAction\b", script):
            script = script.rstrip() + " -ErrorAction SilentlyContinue"
        return f'{m.group("exe")} -Command {m.group("q")}{script}{m.group("q")}'

    return cmd.rstrip() + " -ErrorAction SilentlyContinue"


def _sanitize_outgoing_shell_tool_calls(tool_calls: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    if not tool_calls:
        return tool_calls, 0
    out: list[dict[str, Any]] = []
    fixed = 0
    for tc in tool_calls:
        if not isinstance(tc, dict):
            out.append(tc)
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = str(fn.get("name") or "").strip().lower() if isinstance(fn, dict) else ""
        if name != "shell":
            out.append(tc)
            continue
        args_raw = fn.get("arguments") if isinstance(fn, dict) else None
        args_obj: dict[str, Any] | None = None
        if isinstance(args_raw, str):
            try:
                parsed = json.loads(args_raw)
                if isinstance(parsed, dict):
                    args_obj = parsed
            except json.JSONDecodeError:
                args_obj = None
        elif isinstance(args_raw, dict):
            args_obj = dict(args_raw)
        if not isinstance(args_obj, dict):
            out.append(tc)
            continue
        cmd = args_obj.get("command")
        if not isinstance(cmd, str):
            out.append(tc)
            continue
        safe_cmd = _ensure_safe_windows_listing_command(cmd)
        if safe_cmd == cmd:
            out.append(tc)
            continue
        args_obj["command"] = safe_cmd
        fn2 = dict(fn)
        fn2["arguments"] = json.dumps(args_obj, ensure_ascii=False)
        tc2 = dict(tc)
        tc2["function"] = fn2
        out.append(tc2)
        fixed += 1
    return out, fixed


def _extract_tool_call_thought_signature(tc: dict[str, Any], fn: dict[str, Any]) -> str:
    candidates: list[Any] = []
    if isinstance(fn, dict):
        candidates.extend((fn.get("thought_signature"), fn.get("thoughtSignature")))
    candidates.extend((tc.get("thought_signature"), tc.get("thoughtSignature")))
    extra = tc.get("extra_content")
    if isinstance(extra, dict):
        google = extra.get("google")
        if isinstance(google, dict):
            candidates.extend((google.get("thought_signature"), google.get("thoughtSignature")))
    for raw in candidates:
        if isinstance(raw, str):
            s = raw.strip()
            if s:
                return s
    return ""


def _extract_tool_call_function_name(tc: dict[str, Any]) -> str:
    fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
    return _sanitize_tool_name(fn.get("name") if isinstance(fn, dict) else None, fallback="")


def _persist_gemini_tool_calls_state(
    *,
    tool_calls: list[Any] | None,
    model_name: str | None,
    trace_id: str | None,
    db_path: str | None,
) -> int:
    if not _is_gemini_model_name(model_name):
        return 0
    if not isinstance(tool_calls, list) or not tool_calls:
        return 0
    model = str(model_name or "").strip() or "gemini"
    rows: list[dict[str, str]] = []
    for tc in tool_calls:
        if not isinstance(tc, dict):
            continue
        call_id = _message_tool_call_id(tc)
        if not call_id:
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        name = _extract_tool_call_function_name(tc)
        sig = _extract_tool_call_thought_signature(tc, fn if isinstance(fn, dict) else {})
        rows.append(
            {
                "call_id": call_id,
                "model": model,
                "function_name": name,
                "thought_signature": sig,
                "trace_id": str(trace_id or ""),
            }
        )
    if not rows:
        return 0
    return _gemini_tool_state_upsert_many(db_path or _resolve_default_webui_db_path(), rows=rows)


def _sse_tool_calls_payload(tool_calls: list[Any]) -> list[dict[str, object]]:
    payload_calls: list[dict[str, object]] = []
    for i, tc in enumerate(tool_calls):
        if not isinstance(tc, dict):
            continue
        fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
        fn_payload: dict[str, object] = {
            "name": fn.get("name"),
            "arguments": fn.get("arguments"),
        }
        call_id = tc.get("id") if tc.get("id") is not None else tc.get("call_id")
        call_payload: dict[str, object] = {
            "index": i,
            "id": call_id,
            "call_id": call_id,
            "type": "function",
            "function": fn_payload,
        }
        thought_signature = _extract_tool_call_thought_signature(tc, fn)
        extra = tc.get("extra_content")
        extra_out = dict(extra) if isinstance(extra, dict) else {}
        if thought_signature:
            fn_payload["thought_signature"] = thought_signature
            google = extra_out.get("google")
            if isinstance(google, dict):
                google_out = dict(google)
            else:
                google_out = {}
            google_out.setdefault("thought_signature", thought_signature)
            extra_out["google"] = google_out
        if extra_out:
            call_payload["extra_content"] = extra_out
        payload_calls.append(call_payload)
    return payload_calls

