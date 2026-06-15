#!/usr/bin/env bash
# Linux startup smoke (Phase 5) — build CoreUI, verify imports, optional health poll.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> CoreUI build"
(cd CoreModules/CoreUI && npm ci && npm run build)

echo "==> Python import smoke"
python -m pytest -q tests/scripts/test_import_smoke.py

echo "==> Ruff (syntax + imports)"
ruff check .

echo "==> Fast pytest subset"
pytest -q -m fast --maxfail=3 -x

echo "PASS: startup_smoke.sh"
