from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if root not in sys.path:
    sys.path.insert(0, root)


@pytest.fixture(autouse=True)
def _workspace_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("llm_proxy.workspace._workspace_root_fn", lambda: Path(root))


from llm_proxy.chat_completions_nonstream_response import resolve_legacy_nonstream_tool_calls
from llm_proxy.chat_completions_rag_prep import build_rag_metadata_for_response


def test_build_rag_metadata_for_response_includes_optional_fields() -> None:
    class RagCtx:
        chunks_info = [{"id": 1}]
        max_score = 0.9
        rag_trace = [{"step": "search"}]
        coverage_report = {"ok": True}
        rag_quality = {"score": 1}

    payload = build_rag_metadata_for_response(RagCtx())
    assert payload["chunks_count"] == 1
    assert payload["rag_trace"] == [{"step": "search"}]
    assert payload["coverage_report"] == {"ok": True}
    assert payload["rag_quality"] == {"score": 1}


def test_resolve_legacy_nonstream_tool_calls_extracts_edit() -> None:
    content = json.dumps(
        {
            "file_path": "src/main.py",
            "content": "print('hello')",
        }
    )
    tool_calls, resolved_content = resolve_legacy_nonstream_tool_calls(
        content=content,
        tools=[{"type": "function", "function": {"name": "edit_file"}}],
        tool_choice_effective="auto",
        post_tool_success_turn=False,
        stream=False,
        build_sse_streaming=True,
        selected_edit_tool_name="edit_file",
        selected_edit_tool={"type": "function", "function": {"name": "edit_file", "parameters": {"properties": {"content": {}}}}},
        selected_tool_write_capable=True,
        user_query="edit src/main.py",
    )
    assert len(tool_calls) == 1
    assert tool_calls[0]["function"]["name"] == "edit_file"
    assert resolved_content == content


def test_resolve_legacy_nonstream_tool_calls_skips_post_tool_turn() -> None:
    tool_calls, content = resolve_legacy_nonstream_tool_calls(
        content='{"file_path":"a.py","content":"x"}',
        tools=[{"type": "function"}],
        tool_choice_effective="auto",
        post_tool_success_turn=True,
        stream=False,
        build_sse_streaming=True,
        selected_edit_tool_name="edit_file",
        selected_edit_tool=None,
        selected_tool_write_capable=True,
        user_query="",
    )
    assert tool_calls == []
    assert content.startswith("{")


@pytest.mark.fast
def test_resolve_legacy_nonstream_tool_calls_non_write_capable_message() -> None:
    content = json.dumps({"file_path": "a.py", "content": "body"})
    tool_calls, resolved = resolve_legacy_nonstream_tool_calls(
        content=content,
        tools=[{"type": "function"}],
        tool_choice_effective="auto",
        post_tool_success_turn=False,
        stream=False,
        build_sse_streaming=True,
        selected_edit_tool_name="read_file",
        selected_edit_tool=None,
        selected_tool_write_capable=False,
        user_query="edit a.py",
    )
    assert tool_calls == []
    assert "Cannot apply edit" in resolved
