#!/usr/bin/env bash
# Capture mutmut baseline for Linux CI/WSL (advisory). See docs/QUALITY_GATE_PROFILES.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
OUT_DIR="$ROOT/reports/baseline"
OUT_FILE="$OUT_DIR/mutation-baseline.txt"
mkdir -p "$OUT_DIR"

{
  echo "# Mutation baseline (advisory)"
  echo "captured_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "host=$(uname -a 2>/dev/null || echo unknown)"
  python --version 2>&1 || true
  mutmut --version 2>&1 || true
  echo ""
  echo "## mutmut run"
  mutmut run
  echo ""
  echo "## mutmut results"
  mutmut results
  echo ""
  echo "## mutmut score_summary"
  mutmut results 2>&1 | grep -Ei 'killed|survived|timeout|skipped' || true
} | tee "$OUT_FILE"

echo "Wrote $OUT_FILE"
