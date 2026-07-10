"""Tests for mutation baseline score recording."""

from __future__ import annotations

from pathlib import Path

import scripts.record_mutation_baseline_score as record_mutation_baseline_score
from scripts.record_mutation_baseline_score import (
    extract_results_block,
    format_score_file,
    parse_mutmut_results,
)


def test_parse_mutmut_results_counts_statuses() -> None:
    block = """
    domain.foo.x_bar__mutmut_1: killed
    domain.foo.x_bar__mutmut_2: survived
    domain.foo.x_bar__mutmut_3: no tests
    """
    assert parse_mutmut_results(block) == {"killed": 1, "survived": 1, "no tests": 1}


def test_extract_results_block_between_markers() -> None:
    text = (
        "# header\n"
        "captured_at=2026-07-10T00:00:00Z\n"
        "## mutmut results\n"
        "    a.x__mutmut_1: killed\n"
        "## mutmut score_summary\n"
        "    a.x__mutmut_1: killed\n"
    )
    block = extract_results_block(text)
    assert "a.x__mutmut_1: killed" in block


def test_format_score_file_includes_tag_and_percent(tmp_path: Path) -> None:
    rendered = format_score_file(
        tag="v0.8.61",
        captured_at="2026-07-10T13:17:12Z",
        counts={"killed": 2, "survived": 8, "no tests": 1},
        note="stable trend",
    )
    assert "tag=v0.8.61" in rendered
    assert "total=11" in rendered
    assert "mutation_score_pct=18.18" in rendered
    assert "note=stable trend" in rendered


def test_main_writes_score_file(tmp_path: Path, monkeypatch) -> None:
    log = tmp_path / "mutation-baseline.txt"
    out = tmp_path / "score.txt"
    log.write_text(
        "\n".join(
            [
                "captured_at=2026-07-10T13:17:12Z",
                "## mutmut results",
                "    foo.x__mutmut_1: killed",
                "    foo.x__mutmut_2: survived",
                "## mutmut score_summary",
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("GITHUB_REF_NAME", "v0.8.61")
    assert (
        record_mutation_baseline_score.main(
            [str(log), "--output", str(out), "--note", "ci run"],
        )
        == 0
    )
    body = out.read_text(encoding="utf-8")
    assert "tag=v0.8.61" in body
    assert "killed=1" in body
    assert "survived=1" in body
