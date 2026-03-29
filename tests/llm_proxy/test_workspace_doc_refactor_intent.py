"""_workspace_doc_refactor_intent skips RAG/web for local .md extraction tasks."""

from __future__ import annotations

from llm_proxy.tool_helpers import _workspace_doc_refactor_intent


def test_workspace_doc_refactor_intent_matches_todo_post_mvp_scenario() -> None:
    msg = (
        "[@TODO.md (173:182)](file:///C:/Users/Raylee/AI/TODO.md#L173:182)  Вынеси это в новый файл POST_MVP.md "
        "<context><selections></selections></context>"
    )
    assert _workspace_doc_refactor_intent(msg) is True


def test_workspace_doc_refactor_intent_false_without_span() -> None:
    msg = "[@README.md](file:///C:/Users/x/README.md) explain this file\n"
    assert _workspace_doc_refactor_intent(msg) is False


def test_workspace_doc_refactor_intent_false_without_file_ref() -> None:
    msg = "Вынеси раздел в новый файл POST_MVP.md"
    assert _workspace_doc_refactor_intent(msg) is False
