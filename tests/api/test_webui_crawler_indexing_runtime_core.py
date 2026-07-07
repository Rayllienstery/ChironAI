"""Unit tests for crawler indexing runtime helpers."""

from __future__ import annotations

import time

from api.http.webui_crawler_indexing_runtime_core import (
    record_prepare_stats,
    remember_prepare_removal,
    snapshot_indexing_stats,
    touch_collection_job_timing,
)


def test_touch_collection_job_timing_updates_elapsed_fields() -> None:
    job = {"status": "running", "current_phase": "chunking"}
    touch_collection_job_timing(job)
    assert job["elapsed_ms"] >= 0
    assert job["current_phase_elapsed_ms"] >= 0


def test_touch_collection_job_timing_ignores_finished_jobs() -> None:
    job = {"status": "success", "elapsed_ms": 5}
    touch_collection_job_timing(job)
    assert job["elapsed_ms"] == 5


def test_snapshot_indexing_stats_copies_mutable_fields() -> None:
    state = {
        "skip_reasons": {"too_short": 2},
        "errors": ["e1"],
        "recent_skips": [{"reason": "too_short"}],
        "largest_prepare_removals": [{"filename": "a.md"}],
        "embedding_history": [{"path": "a.md"}],
        "_touch_timing": lambda: None,
    }
    snap = snapshot_indexing_stats(state)
    state["skip_reasons"]["too_short"] = 99
    state["errors"].append("e2")
    assert snap["skip_reasons"]["too_short"] == 2
    assert snap["errors"] == ["e1"]
    assert "_touch_timing" not in snap


def test_record_prepare_stats_accumulates_char_counts() -> None:
    state: dict = {}
    record_prepare_stats(
        state,
        {
            "body_original_chars": 100,
            "body_prepared_chars": 80,
            "removed_chars": 20,
        },
    )
    record_prepare_stats(
        state,
        {
            "body_original_chars": 50,
            "body_prepared_chars": 40,
            "removed_chars": 10,
        },
    )
    assert state["prepare_original_chars"] == 150
    assert state["prepare_output_chars"] == 120
    assert state["prepare_removed_chars"] == 30


def test_remember_prepare_removal_keeps_largest_rows() -> None:
    state: dict = {}
    remember_prepare_removal(
        state,
        source_id="docs",
        filename="small.md",
        prepare_stats={"removed_chars": 10},
    )
    remember_prepare_removal(
        state,
        source_id="docs",
        filename="large.md",
        prepare_stats={"removed_chars": 500},
    )
    rows = state["largest_prepare_removals"]
    assert any(row["filename"] == "large.md" for row in rows)
    assert rows[0]["removed_chars"] >= rows[-1]["removed_chars"]
