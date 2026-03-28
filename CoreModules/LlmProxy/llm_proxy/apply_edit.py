"""POST /v1/files/apply-edit — workspace file range replacement."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Response, jsonify, request

from llm_proxy.tool_helpers import _replace_text_range, _resolve_workspace_path

if TYPE_CHECKING:
    from llm_proxy.contracts import LlmProxyWiring


def run_apply_file_edit(w: LlmProxyWiring) -> Response | tuple[Response, int]:
    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"ok": False, "error": "Invalid JSON"}), 400

    try:
        file_path_raw = str(body.get("file_path") or "").strip()
        range_data = body.get("range") or {}
        new_text = body.get("new_text")
        patch_text = body.get("patch")
        dry_run = bool(body.get("dry_run", False))
        if patch_text:
            return jsonify({"ok": False, "error": "patch apply is not supported yet"}), 400
        if not isinstance(range_data, dict):
            return jsonify({"ok": False, "error": "range must be an object"}), 400
        if not isinstance(new_text, str):
            return jsonify({"ok": False, "error": "new_text is required"}), 400

        resolved = _resolve_workspace_path(file_path_raw)
        if not resolved.exists():
            return jsonify({"ok": False, "error": "file does not exist"}), 404
        original = resolved.read_text(encoding="utf-8")

        if "end_col" in range_data:
            lines = original.splitlines(keepends=True)
            end_line = int(range_data.get("end_line") or 0)
            if 1 <= end_line <= len(lines):
                end_col = int(range_data.get("end_col") or 1)
                if end_col > len(lines[end_line - 1]) + 1:
                    range_data = dict(range_data)
                    range_data["end_col"] = len(lines[end_line - 1]) + 1

        updated = _replace_text_range(original, range_data, new_text)
        if not dry_run:
            resolved.write_text(updated, encoding="utf-8")
        try:
            w.get_logs_repository().add_log(
                session_id="proxy",
                level="INFO",
                message=f"Apply edit: {resolved}",
                source="proxy.apply_edit",
                metadata={
                    "file_path": str(resolved),
                    "dry_run": dry_run,
                    "range": range_data,
                    "new_text_len": len(new_text),
                },
            )
        except Exception:
            pass

        return jsonify(
            {
                "ok": True,
                "applied": not dry_run,
                "dry_run": dry_run,
                "file_path": str(resolved),
                "preview": updated[:2000],
            }
        )
    except ValueError as exc:
        try:
            w.get_logs_repository().add_log(
                session_id="proxy",
                level="ERROR",
                message=f"Apply edit failed: {exc}",
                source="proxy.apply_edit",
                metadata={"error": str(exc)},
            )
        except Exception:
            pass
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception as exc:
        return jsonify({"ok": False, "error": str(exc)}), 500
