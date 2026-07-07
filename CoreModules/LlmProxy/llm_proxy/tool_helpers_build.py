"""Tool argument and instruction builders for proxy tools."""

from __future__ import annotations

import re
from pathlib import Path

from llm_proxy.tool_helpers_edit import (
    _client_files_excerpt_and_full_range,
    _extract_file_path_for_edit_tool_precedence,
    _extract_line_span_from_user_text,
    _is_create_intent,
    _is_edit_like_tool_name,
    _normalize_tool_path,
    _resolve_workspace_relative_path_hint,
    _tool_path_from_uri_or_path,
)
from llm_proxy.tool_helpers_results import (
    _coerce_zed_tool_mode,
    _compact_display_description,
    _default_tool_keys,
    _strip_placeholder_edit_lines,
    _sync_edit_file_duplicate_body_fields,
    _tool_args_have_substantive_body,
)
from llm_proxy.workspace import workspace_root as _workspace_root


def _build_tool_arguments(
    *,
    selected_tool_name: str,
    selected_tool: dict[str, object] | None,
    edit_payload: dict[str, object],
    user_query: str,
) -> dict[str, object]:
    user_path = _extract_file_path_for_edit_tool_precedence(user_query or "")
    payload_raw_path = str(edit_payload.get("file_path") or edit_payload.get("path") or "")
    normalized_payload_path = _normalize_tool_path(payload_raw_path) if payload_raw_path else ""
    file_path = normalized_payload_path
    # IDE-independent mode: if the user provided a file URI or absolute path, preserve it verbatim
    # so the client IDE applies the edit on its own machine.
    if isinstance(user_path, str) and user_path:
        up = user_path.strip()
        if up.startswith("file://") or re.match(r"^[A-Za-z]:/", up) or up.startswith("/"):
            file_path = _tool_path_from_uri_or_path(up)
            normalized_payload_path = file_path
    if user_path and file_path:
        try:
            root = _workspace_root()
            if not (root / file_path).exists():
                normalized_user_path = _normalize_tool_path(user_path)
                if normalized_user_path and (root / normalized_user_path).exists():
                    file_path = normalized_user_path
        except Exception:  # safe: workspace path resolution best-effort
            pass
    if user_path and not file_path:
        up2 = user_path.strip()
        if up2.startswith("file://") or re.match(r"^[A-Za-z]:/", up2) or up2.startswith("/"):
            file_path = _tool_path_from_uri_or_path(up2)
        else:
            file_path = _normalize_tool_path(user_path)
    # If the model returned a relative hint (e.g. Desktop/test.swift) but the user provided
    # an absolute file:///C:/... path, prefer the user's absolute path (even if outside workspace).
    if (
        user_path
        and file_path
        and not file_path.startswith("file://")
        and not re.match(r"^[A-Za-z]:/", file_path)
        and not file_path.startswith("/")
    ):
        normalized_user_path = _normalize_tool_path(user_path)
        if re.match(r"^[A-Za-z]:/", normalized_user_path) or normalized_user_path.startswith("/"):
            file_path = normalized_user_path
    if file_path and "/" not in file_path:
        file_path = _resolve_workspace_relative_path_hint(file_path)
    # Final guard: keep client-machine path semantics, but convert file:// URI to tool-local path.
    if isinstance(user_path, str) and user_path.strip().startswith("file://"):
        file_path = _tool_path_from_uri_or_path(user_path.strip())
    range_obj = edit_payload.get("range") if isinstance(edit_payload.get("range"), dict) else {}
    # If model omitted range but user explicitly selected lines, prefer range edit over full overwrite.
    if not range_obj:
        span = _extract_line_span_from_user_text(user_query or "")
        if span:
            a, b = span
            range_obj = {
                "start_line": int(a),
                "start_col": 1,
                "end_line": int(b),
                "end_col": 1,
            }
    # If no explicit selection range, but client attached full file content (<files> block),
    # derive a safe full-file range to avoid destructive overwrite behavior.
    has_client_file_excerpt = False
    if not range_obj:
        _ex_files, _range_files = _client_files_excerpt_and_full_range(user_query or "")
        if _ex_files and _range_files:
            has_client_file_excerpt = True
            range_obj = dict(_range_files)
    new_text = str(
        edit_payload.get("new_text")
        or edit_payload.get("content")
        or edit_payload.get("replacement")
        or ""
    )
    desc = _compact_display_description(user_query or "")
    if not desc:
        desc = f"Apply requested edit via {selected_tool_name}"
    display_description = desc[:180]

    raw_mode = (
        edit_payload.get("mode")
        or edit_payload.get("operation")
        or edit_payload.get("variant")
    )
    mode_value = (
        _coerce_zed_tool_mode(raw_mode)
        if raw_mode not in (None, "")
        else ("create" if _is_create_intent(user_query) else "edit")
    )
    has_range = bool(range_obj)
    tool_name_l = (selected_tool_name or "").lower()
    # Zed may treat `edit_file` without `range` as a no-op unless we switch to full-file modes.
    # When model asks for `mode=edit` but provides no `range`, prefer `overwrite` (existing file)
    # or `create` (missing file) to ensure Swift/Desktop files get written.
    if mode_value == "edit" and not has_range and (
        "edit_file" in tool_name_l or "apply_file_edit" in tool_name_l
    ):
        # If we derived a safe range from client file excerpt, keep mode=edit.
        if has_client_file_excerpt:
            mode_value = "edit"
        else:
            try:
                fp_for_exists = file_path
                if isinstance(fp_for_exists, str) and fp_for_exists.startswith("file:///"):
                    fp_for_exists = fp_for_exists[8:]
                p = Path(fp_for_exists)
                exists = p.exists() if p.is_absolute() else (_workspace_root() / fp_for_exists).exists()
            except Exception:
                exists = False
            mode_value = "overwrite" if exists else "create"

    # Models often return mode=overwrite together with a line range. Some IDEs treat overwrite as
    # "replace the whole file", ignoring range, which truncates the file to the fragment.
    if (
        mode_value == "overwrite"
        and has_range
        and ("edit_file" in tool_name_l or "apply_file_edit" in tool_name_l)
    ):
        try:
            fp_for_exists2 = file_path
            if isinstance(fp_for_exists2, str) and fp_for_exists2.startswith("file:///"):
                fp_for_exists2 = fp_for_exists2[8:]
            p2 = Path(fp_for_exists2)
            exists2 = p2.exists() if p2.is_absolute() else (_workspace_root() / fp_for_exists2).exists()
        except Exception:
            exists2 = False
        if exists2:
            mode_value = "edit"

    canonical_values: dict[str, object] = {
        "file_path": file_path,
        "path": file_path,
        "target_file": file_path,
        "new_text": new_text,
        "replacement": new_text,
        "text": new_text,
        "content": new_text,
        "new_content": new_text,
        "range": range_obj,
        "line_range": range_obj,
        "location": range_obj,
        "start_line": range_obj.get("start_line"),
        "end_line": range_obj.get("end_line"),
        "start_col": range_obj.get("start_col"),
        "end_col": range_obj.get("end_col"),
        "display_description": display_description,
        "mode": mode_value,
        "operation": mode_value,
        "variant": mode_value,
    }

    # If tool schema provides required keys, ensure they are present to avoid Zed-side rejection.
    properties: dict[str, object] = {}
    required: list[str] = []
    try:
        fn = selected_tool.get("function") if isinstance(selected_tool, dict) else None
        params = fn.get("parameters") if isinstance(fn, dict) else None
        if isinstance(params, dict) and isinstance(params.get("properties"), dict):
            properties = params.get("properties")  # type: ignore[assignment]
        if isinstance(params, dict) and isinstance(params.get("required"), list):
            required = [str(x) for x in params.get("required") if isinstance(x, str)]
    except Exception:
        required = []

    # Strict native mode: only schema keys (+ required keys) are emitted.
    keys_to_emit: set[str] = set(required)
    keys_to_emit.update(str(k) for k in properties)
    if not keys_to_emit:
        keys_to_emit = set(_default_tool_keys(selected_tool_name))

    # Special handling for save-file batch payload (`paths`).
    # Some clients require tool input like:
    #   paths=[{"path": "...", "content": "..."}]
    # rather than a single `path`.
    if "paths" in keys_to_emit:
        paths_items_type = ""
        try:
            pdef = properties.get("paths") if isinstance(properties, dict) else None
            if isinstance(pdef, dict):
                items = pdef.get("items")
                if isinstance(items, dict):
                    t = items.get("type")
                    if isinstance(t, str):
                        paths_items_type = t.strip().lower()
        except Exception:
            paths_items_type = ""
        payload_paths = edit_payload.get("paths")
        if isinstance(payload_paths, list):
            if paths_items_type == "string":
                normalized_path_strings: list[str] = []
                for p in payload_paths:
                    if isinstance(p, dict):
                        p_path_raw = p.get("path") or p.get("file_path") or ""
                        p_path = _normalize_tool_path(str(p_path_raw)) if p_path_raw else ""
                        if p_path:
                            normalized_path_strings.append(p_path)
                    elif isinstance(p, str):
                        p_path = _normalize_tool_path(p) if p else ""
                        if p_path:
                            normalized_path_strings.append(p_path)
                canonical_values["paths"] = normalized_path_strings
            else:
                normalized_paths: list[dict[str, object]] = []
                for p in payload_paths:
                    if isinstance(p, dict):
                        p_path_raw = p.get("path") or p.get("file_path") or ""
                        p_content_raw = (
                            p.get("content")
                            or p.get("new_text")
                            or p.get("text")
                            or new_text
                        )
                        p_path = _normalize_tool_path(str(p_path_raw)) if p_path_raw else ""
                        p_content = str(p_content_raw) if p_content_raw is not None else ""
                        normalized_paths.append({"path": p_path, "content": p_content})
                    elif isinstance(p, str):
                        normalized_paths.append(
                            {"path": _normalize_tool_path(p) if p else "", "content": new_text}
                        )
                canonical_values["paths"] = normalized_paths
        elif file_path:
            if paths_items_type == "string":
                canonical_values["paths"] = [file_path]
            else:
                canonical_values["paths"] = [{"path": file_path, "content": new_text}]

    args: dict[str, object] = {}
    for key in keys_to_emit:
        if key in canonical_values and canonical_values[key] not in (None, ""):
            args[key] = canonical_values[key]
        elif key in edit_payload:
            # Passthrough: preserve client/model-provided fields that aren't derived
            # by canonical_values (helps with schema variations).
            val = edit_payload.get(key)
            if val not in (None, ""):
                if key in ("path", "file_path", "target_file") and not isinstance(val, str):
                    args[key] = str(val)
                else:
                    args[key] = val

    # Guarantee required fields are present, with conservative defaults.
    for key in required:
        if key in args and args.get(key) not in (None, ""):
            continue
        if key in canonical_values:
            args[key] = canonical_values[key]
        elif key in edit_payload and edit_payload.get(key) not in (None, ""):
            args[key] = edit_payload.get(key)  # type: ignore[assignment]
        elif key == "display_description":
            args[key] = display_description
        else:
            args[key] = [] if key == "paths" else ""

    # Zed rejects empty string for enum `mode` (edit/create/overwrite).
    for k in ("mode", "operation", "variant"):
        if k not in args:
            continue
        v = args.get(k)
        if v is None or (isinstance(v, str) and not v.strip()):
            args[k] = "edit"
        else:
            args[k] = _coerce_zed_tool_mode(v)

    for _k in ("replacement", "new_text", "content", "text", "new_content"):
        if _k in args and isinstance(args[_k], str):
            args[_k] = _strip_placeholder_edit_lines(args[_k])

    # If schema-key filtering dropped body fields, but model produced valid edit text,
    # inject a best-effort text field so IDE tools can still apply the edit.
    if _is_edit_like_tool_name(selected_tool_name) and not _tool_args_have_substantive_body(
        selected_tool_name, args
    ):
        fallback_text = str(
            edit_payload.get("new_text")
            or edit_payload.get("content")
            or edit_payload.get("replacement")
            or ""
        )
        if fallback_text.strip():
            n = (selected_tool_name or "").lower()
            if "replace" in n and "range" in n:
                args["replacement"] = fallback_text
            elif "new_text" in keys_to_emit:
                args["new_text"] = fallback_text
            elif "content" in keys_to_emit:
                args["content"] = fallback_text
            else:
                # Loose schemas often still accept `content`.
                args["content"] = fallback_text

    # Compatibility: some clients omit `range` from schema but still require it for mode=edit.
    # If we have a known range (from model or user selection), always include it for edit_file-like tools.
    if _is_edit_like_tool_name(selected_tool_name):
        n = (selected_tool_name or "").lower()
        if ("edit_file" in n or "apply_file_edit" in n) and isinstance(range_obj, dict) and range_obj:
            if not isinstance(args.get("range"), dict) or not args.get("range"):
                args["range"] = range_obj
            if "start_line" in range_obj and args.get("start_line") in (None, "", 0):
                args["start_line"] = range_obj.get("start_line")
            if "end_line" in range_obj and args.get("end_line") in (None, "", 0):
                args["end_line"] = range_obj.get("end_line")
            if "start_col" in range_obj and args.get("start_col") in (None, "", 0):
                args["start_col"] = range_obj.get("start_col")
            if "end_col" in range_obj and args.get("end_col") in (None, "", 0):
                args["end_col"] = range_obj.get("end_col")

    # Compatibility: many edit_file implementations accept either `content` or `new_text`.
    # Send both when we have text to avoid client-side empty-overwrite behavior.
    if _is_edit_like_tool_name(selected_tool_name):
        n = (selected_tool_name or "").lower()
        if "edit_file" in n or "apply_file_edit" in n:
            _sync_edit_file_duplicate_body_fields(args)

    # Drop empty body strings so clients do not prefer an empty field over a filled one.
    if _is_edit_like_tool_name(selected_tool_name):
        for bk in ("replacement", "new_text", "content", "text", "new_content"):
            if bk in args and isinstance(args[bk], str) and not str(args[bk]).strip():
                del args[bk]
        n = (selected_tool_name or "").lower()
        if "edit_file" in n or "apply_file_edit" in n:
            _sync_edit_file_duplicate_body_fields(args)

    return args


def _build_tool_json_instruction(
    selected_tool_name: str | None,
    selected_tool: dict[str, object] | None,
) -> str:
    if not selected_tool_name:
        return ""
    fn: dict[str, object] = {}
    if isinstance(selected_tool, dict):
        maybe_fn = selected_tool.get("function")
        if isinstance(maybe_fn, dict):
            fn = maybe_fn  # type: ignore[assignment]
    params = fn.get("parameters") if isinstance(fn, dict) else {}
    required = (
        params.get("required")
        if isinstance(params, dict) and isinstance(params.get("required"), list)
        else []
    )
    properties = (
        params.get("properties")
        if isinstance(params, dict) and isinstance(params.get("properties"), dict)
        else {}
    )
    prop_names = [str(k) for k in properties]
    req_names = [str(x) for x in required if isinstance(x, str)]
    fields = req_names if req_names else prop_names
    if not fields:
        fields = sorted(_default_tool_keys(selected_tool_name))
    n = (selected_tool_name or "").lower()
    tail = ""
    if "replace" in n and "range" in n:
        tail = (
            " Required: non-empty `replacement` with the full multi-line text that replaces the user’s selected "
            "line range (not a description)."
        )
    elif "edit" in n and "file" in n:
        tail = (
            " Required for `edit` mode: non-empty `content` or `new_text` with the actual source code to apply "
            "(not just path/description/mode)."
        )
    return (
        "Tool-call mode is enabled. "
        f"Return ONLY a single valid JSON object for tool `{selected_tool_name}` with fields from tool schema: {fields}. "
        "Do not return markdown, code fences, comments, or explanations. "
        "Use workspace-relative path in `path`/`file_path` when applicable. "
        "If the schema includes `mode`, it must be exactly one of: edit, create, overwrite (never empty). "
        "Do not emit placeholder lines such as `// removed` or `// ...` in `content`/`replacement`; output only real source lines."
        f"{tail}"
    )


