"""Edit-tool path hint: destination file when user asks to copy/append across two file refs."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root not in sys.path:
    sys.path.insert(0, root)


def test_extract_file_path_for_edit_prefers_last_uri_on_copy_to_end(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("llm_proxy.workspace._workspace_root_fn", lambda: Path(root))
    from llm_proxy.tool_helpers import (
        _extract_file_path_for_edit_tool_precedence,
        _build_tool_arguments,
    )

    f1 = Path(root) / "tests" / "_tmp_path_prec_a.md"
    f2 = Path(root) / "tests" / "_tmp_path_prec_b.md"
    try:
        f1.write_text("src\n", encoding="utf-8")
        f2.write_text("dest\n", encoding="utf-8")
        u1 = f1.as_uri()
        u2 = f2.as_uri()
        msg = f"[@File1.md]({u1}#L1:1) copy to the end of [@File2.md]({u2})"
        assert _extract_file_path_for_edit_tool_precedence(msg) == u2

        args = _build_tool_arguments(
            selected_tool_name="edit_file",
            selected_tool={
                "function": {
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "path": {"type": "string"},
                            "mode": {"type": "string"},
                            "content": {"type": "string"},
                        },
                        "required": ["path", "mode", "content"],
                    },
                },
            },
            edit_payload={
                "path": str(f1.resolve()),
                "mode": "edit",
                "content": "APPEND\n",
                "range": {"start_line": 1, "start_col": 1, "end_line": 10, "end_col": 1},
            },
            user_query=msg,
        )
        out_norm = str(args.get("path") or "").replace("\\", "/")
        assert f2.name in out_norm or str(f2.resolve()).replace("\\", "/") in out_norm
        assert str(f1.resolve()).replace("\\", "/") not in out_norm
    finally:
        for p in (f1, f2):
            if p.exists():
                p.unlink()


def test_native_multifile_append_hint_lists_dest_and_forbids_shell_copy() -> None:
    from llm_proxy.tool_helpers import _native_multifile_append_system_hint

    msg = (
        "[@File1.md (1:1)](file:///C:/Users/Raylee/Desktop/Test/File1.md#L1:1)\n"
        " copy to the end of file \n"
        "[@File2.md](file:///C:/Users/Raylee/Desktop/Test/File2.md)\n"
    )
    h = _native_multifile_append_system_hint(msg)
    assert h
    assert "File2.md" in h
    assert "File1.md" in h
    assert "_end" in h
    assert "shell" in h.lower()


def test_native_multifile_append_hint_none_without_second_uri() -> None:
    from llm_proxy.tool_helpers import _native_multifile_append_system_hint

    assert _native_multifile_append_system_hint("copy to end [@a](file:///C:/only.md)") is None


def test_insert_system_before_last_user() -> None:
    from llm_proxy.tool_helpers import _insert_system_before_last_user_message

    msgs: list = [
        {"role": "system", "content": "a"},
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "ok"},
        {"role": "user", "content": "u2"},
    ]
    _insert_system_before_last_user_message(msgs, "HINT")
    assert msgs[3] == {"role": "system", "content": "HINT"}
    assert msgs[4] == {"role": "user", "content": "u2"}


def test_single_file_still_uses_first_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("llm_proxy.workspace._workspace_root_fn", lambda: Path(root))
    from llm_proxy.tool_helpers import _extract_file_path_for_edit_tool_precedence

    f1 = Path(root) / "tests" / "_tmp_path_single.md"
    try:
        f1.write_text("x\n", encoding="utf-8")
        u1 = f1.as_uri()
        msg = f"[@Only.md]({u1}) fix typo"
        assert _extract_file_path_for_edit_tool_precedence(msg) == u1
    finally:
        if f1.exists():
            f1.unlink()
