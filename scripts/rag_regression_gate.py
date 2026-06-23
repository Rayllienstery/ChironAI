"""
Regression gate for Apple_Collection quality.

Usage:
  python scripts/rag_regression_gate.py

Fails (exit code 1) when thresholds are not met.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT_JSON = ROOT / "logs" / "apple_collection_post_reindex_audit.json"


def main() -> int:
    if not AUDIT_JSON.is_file():
        print(f"Missing audit JSON: {AUDIT_JSON}", file=sys.stderr)
        return 2
    data = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
    stats = data.get("stats") or {}
    probes = data.get("probes") or []

    pass_n = sum(1 for p in probes if p.get("verdict") == "PASS")
    partial_n = sum(1 for p in probes if p.get("verdict") == "PARTIAL")
    fail_n = sum(1 for p in probes if p.get("verdict") == "FAIL")

    dup_pct = float(stats.get("dup_pct") or 0.0)
    doc_scope_pct = float(stats.get("doc_scope_filled_pct") or 0.0)
    short_pct = float(stats.get("short_lt_300_pct") or 0.0)

    # Thresholds: start strict, tune when we reach targets once.
    thresholds = {
        "probes_pass_min": 10,
        "probes_fail_max": 0,
        "dup_pct_max": 2.0,
        "doc_scope_filled_min": 65.0,
        "short_lt_300_pct_max": 3.0,
    }

    problems: list[str] = []
    if pass_n < thresholds["probes_pass_min"]:
        problems.append(f"PASS probes {pass_n} < {thresholds['probes_pass_min']}")
    if fail_n > thresholds["probes_fail_max"]:
        problems.append(f"FAIL probes {fail_n} > {thresholds['probes_fail_max']}")
    if dup_pct > thresholds["dup_pct_max"]:
        problems.append(f"dup_pct {dup_pct} > {thresholds['dup_pct_max']}")
    if doc_scope_pct < thresholds["doc_scope_filled_min"]:
        problems.append(f"doc_scope_filled_pct {doc_scope_pct} < {thresholds['doc_scope_filled_min']}")
    if short_pct > thresholds["short_lt_300_pct_max"]:
        problems.append(f"short_lt_300_pct {short_pct} > {thresholds['short_lt_300_pct_max']}")

    summary = {
        "pass": pass_n,
        "partial": partial_n,
        "fail": fail_n,
        "dup_pct": dup_pct,
        "doc_scope_filled_pct": doc_scope_pct,
        "short_lt_300_pct": short_pct,
        "thresholds": thresholds,
        "ok": not problems,
        "problems": problems,
    }
    print(json.dumps(summary, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())

