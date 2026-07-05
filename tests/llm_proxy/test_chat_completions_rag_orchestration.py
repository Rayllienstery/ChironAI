from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from llm_proxy.chat_completions_rag_orchestration import (
    resolve_project_context_collections,
    resolve_skip_rag_retrieval,
)


def test_resolve_skip_rag_retrieval_autocomplete() -> None:
    result = resolve_skip_rag_retrieval(
        body={},
        last_user="edit file",
        tools=[{"type": "function"}],
        selected_edit_tool_name="edit_file",
        tool_choice_effective="auto",
        use_native_tools=False,
        force_rag=False,
        fetch_web_knowledge=False,
        request_collection=None,
        post_tool_success_turn=False,
        is_autocomplete=True,
        dumb_build_pipeline=False,
        proxy_settings={"rag_enabled": True},
    )
    assert result.skip_rag_retrieval is True


def test_resolve_skip_rag_retrieval_local_tool_edit_fast_path() -> None:
    result = resolve_skip_rag_retrieval(
        body={},
        last_user="[@src/main.py (10:20)](file:///C:/proj/src/main.py) replace this block",
        tools=[{"type": "function"}],
        selected_edit_tool_name="edit_file",
        tool_choice_effective="auto",
        use_native_tools=False,
        force_rag=False,
        fetch_web_knowledge=False,
        request_collection=None,
        post_tool_success_turn=False,
        is_autocomplete=False,
        dumb_build_pipeline=False,
        proxy_settings={"rag_enabled": True},
    )
    assert result.skip_rag_retrieval is True
    assert result.local_tool_edit_fast_path is True


def test_resolve_project_context_collections_without_fetch_web() -> None:
    w = MagicMock()
    result = resolve_project_context_collections(
        w=w,
        fetch_web_knowledge=False,
        project_context={"frameworks": [{"name": "react"}]},
    )
    assert result.project_fresh_collection_names is None
    assert result.needs_refresh == []


@pytest.mark.fast
def test_resolve_skip_rag_retrieval_explicit_skip() -> None:
    result = resolve_skip_rag_retrieval(
        body={"skip_rag": True},
        last_user="hello",
        tools=[],
        selected_edit_tool_name=None,
        tool_choice_effective="none",
        use_native_tools=False,
        force_rag=False,
        fetch_web_knowledge=False,
        request_collection=None,
        post_tool_success_turn=False,
        is_autocomplete=False,
        dumb_build_pipeline=False,
        proxy_settings={"rag_enabled": True},
    )
    assert result.skip_rag_retrieval is True


def test_resolve_skip_rag_retrieval_build_rag_disabled() -> None:
    result = resolve_skip_rag_retrieval(
        body={},
        last_user="Explain Swift concurrency",
        tools=[],
        selected_edit_tool_name=None,
        tool_choice_effective="none",
        use_native_tools=False,
        force_rag=False,
        fetch_web_knowledge=False,
        request_collection=None,
        post_tool_success_turn=False,
        is_autocomplete=False,
        dumb_build_pipeline=True,
        proxy_settings={"rag_enabled": False, "rag_collection": "ignored-docs"},
    )
    assert result.skip_rag_retrieval is True
