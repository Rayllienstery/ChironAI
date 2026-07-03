"""Tests for proxy journal grouping and upsert in LogsRepository."""

from __future__ import annotations

from pathlib import Path

import infrastructure.database.session_manager as session_manager_module
from infrastructure.database.logs_repository import LogsRepository


def _make_repo(db_path: Path) -> LogsRepository:
    session_manager_module._session_manager = None
    return LogsRepository(db_path)


def _meta(*, chain: str, trace_id: str, query: str) -> dict:
    return {
        "user_query": query,
        "trace_id": trace_id,
        "trace": {"request": {"trace_chain_id": chain, "client_request_id": chain}},
    }


def test_upsert_proxy_journal_log_merges_agent_steps(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "webui.db")
    chain = "agent-task-1"
    first_id = repo.upsert_proxy_journal_log(
        message="step 1",
        metadata=_meta(chain=chain, trace_id="trace-1", query="same task"),
        trace_chain_id=chain,
    )
    second_id = repo.upsert_proxy_journal_log(
        message="step 2",
        metadata=_meta(chain=chain, trace_id="trace-2", query="same task"),
        trace_chain_id=chain,
    )
    assert second_id == first_id
    rows = repo.get_proxy_journal_groups(limit=10, offset=0)
    assert len(rows) == 1
    assert rows[0]["metadata"]["agent_step_count"] == 2
    assert rows[0]["metadata"]["trace_id"] == "trace-2"


def test_get_proxy_journal_groups_collapses_legacy_rows(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "webui.db")
    chain = "legacy-chain"
    for idx in range(3):
        repo.add_log(
            session_id="proxy",
            level="INFO",
            source="proxy",
            message=f"step {idx}",
            metadata=_meta(chain=chain, trace_id=f"trace-{idx}", query="legacy task"),
        )
    groups = repo.get_proxy_journal_groups(limit=10, offset=0)
    assert len(groups) == 1
    assert groups[0]["metadata"]["agent_step_count"] == 3
    assert repo.count_proxy_journal_groups() == 1


def test_get_proxy_journal_groups_collapses_rows_with_same_prompt_without_chain(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path / "webui.db")
    query = "Add version text to the GPU panel"
    for idx in range(4):
        repo.add_log(
            session_id="proxy",
            level="INFO",
            source="proxy",
            message=f"step {idx}",
            metadata={
                "user_query": query,
                "trace_id": f"trace-{idx}",
                "model": "kimi-k2.5-code:cloud",
                "proxy_backend": "rag_fusion",
            },
        )
    groups = repo.get_proxy_journal_groups(limit=10, offset=0)
    assert len(groups) == 1
    assert groups[0]["metadata"]["agent_step_count"] == 4
    assert repo.count_proxy_journal_groups() == 1
