#!/usr/bin/env bash
# Capture mutmut baseline for Linux CI/WSL (advisory). See docs/QUALITY_GATE_PROFILES.md.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$(python scripts/print_quality_gate_pythonpath.py)"

cleanup_staging() {
  rm -rf domain rag_service
}
trap cleanup_staging EXIT

rm -rf domain rag_service mutants
# Stage import-aligned package trees (mutmut keys must match pytest imports).
cp -a Core/domain domain
cp -a CoreModules/RagService/rag_service rag_service
# mutmut 3.6 copy_also_copy_files() uses shutil.copy2 without mkdir parents
mkdir -p mutants/tests
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

TAG_ARG=()
if [[ -n "${GITHUB_REF_NAME:-}" && "${GITHUB_REF_NAME}" == v* ]]; then
  TAG_ARG=(--tag "${GITHUB_REF_NAME}")
fi
python scripts/record_mutation_baseline_score.py "$OUT_FILE" "${TAG_ARG[@]}"

echo "Wrote $OUT_FILE"
