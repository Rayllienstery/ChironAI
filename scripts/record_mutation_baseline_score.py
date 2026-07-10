"""Parse mutmut baseline log and update docs/mutation-baseline-score.txt."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCORE_FILE = REPO_ROOT / "docs" / "mutation-baseline-score.txt"
RESULTS_START = "## mutmut results"
SCORE_SUMMARY_START = "## mutmut score_summary"


def parse_mutmut_results(block: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in block.splitlines():
        if ": " not in line:
            continue
        status = line.rsplit(": ", 1)[-1].strip()
        if not status:
            continue
        counts[status] = counts.get(status, 0) + 1
    return counts


def extract_results_block(text: str) -> str:
    if RESULTS_START not in text:
        raise ValueError(f"missing {RESULTS_START!r} section")
    start = text.index(RESULTS_START) + len(RESULTS_START)
    if start < len(text) and text[start] == "\n":
        start += 1
    end = text.index(SCORE_SUMMARY_START, start) if SCORE_SUMMARY_START in text else len(text)
    return text[start:end]


def extract_captured_at(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("captured_at="):
            return line.split("=", 1)[1].strip()
    return ""


def normalize_tag(raw: str | None) -> str:
    if not raw:
        return ""
    value = raw.strip()
    if value.startswith("refs/tags/"):
        return value.removeprefix("refs/tags/")
    return value


def resolve_tag(explicit: str | None) -> str:
    if explicit:
        return normalize_tag(explicit)
    for env_name in ("GITHUB_REF_NAME", "CI_TAG"):
        env_value = os.getenv(env_name, "").strip()
        if env_value.startswith("v"):
            return env_value
    return ""


def format_score_file(
    *,
    tag: str,
    captured_at: str,
    counts: dict[str, int],
    note: str,
) -> str:
    killed = counts.get("killed", 0)
    survived = counts.get("survived", 0)
    timeout = counts.get("timeout", 0)
    skipped = counts.get("skipped", 0)
    no_tests = counts.get("no tests", 0)
    total = sum(counts.values())
    score_pct = round(100.0 * killed / total, 2) if total else 0.0
    status = f"ok_{tag}" if tag else "ok"

    lines = [
        "# Mutation baseline score (advisory)",
        "",
        "Updated from tag CI `release` job via `scripts/capture_mutation_baseline.sh`.",
        "Full log: `mutation-baseline.txt` (CI artifact on `v*` tags).",
        "",
        f"status={status}",
        f"captured_at={captured_at}",
    ]
    if tag:
        lines.append(f"tag={tag}")
    lines.extend(
        [
            f"killed={killed}",
            f"survived={survived}",
            f"timeout={timeout}",
            f"skipped={skipped}",
            f"no_tests={no_tests}",
            f"total={total}",
            f"mutation_score_pct={score_pct}",
            f"note={note}",
            "",
        ]
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline_log", type=Path, help="Path to mutation-baseline.txt")
    parser.add_argument("--tag", default=None, help="Release tag (default: GITHUB_REF_NAME when v*)")
    parser.add_argument(
        "--output",
        type=Path,
        default=SCORE_FILE,
        help="Score tracker path (default: docs/mutation-baseline-score.txt)",
    )
    parser.add_argument(
        "--note",
        default="Auto-recorded from capture_mutation_baseline.sh.",
        help="Free-form note stored in the tracker file",
    )
    args = parser.parse_args(argv)

    text = args.baseline_log.read_text(encoding="utf-8")
    counts = parse_mutmut_results(extract_results_block(text))
    if not counts:
        print("No mutmut result lines found; score file not updated.", file=sys.stderr)
        return 1

    tag = resolve_tag(args.tag)
    captured_at = extract_captured_at(text)
    args.output.write_text(
        format_score_file(tag=tag, captured_at=captured_at, counts=counts, note=args.note),
        encoding="utf-8",
    )
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
