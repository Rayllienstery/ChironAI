#!/usr/bin/env bash
set -e

# Run from the repository root even when started from another directory.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO_ROOT"

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON="$REPO_ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON=python3
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  echo "ERROR: Python is not in PATH. Activate your Python environment first." >&2
  exit 1
fi

echo "Building the React frontend..."
if ! "$PYTHON" "$REPO_ROOT/scripts/coreui_build_if_needed.py"; then
  echo >&2
  echo "[build_and_run] Build failed; server was not started." >&2
  exit 1
fi

export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/Core:$REPO_ROOT/Core/modules/webui_backend${PYTHONPATH:+:$PYTHONPATH}"

if [[ -z "${HERMES_HOME:-}" && -d "$HOME/.hermes" ]]; then
  export HERMES_HOME="$HOME/.hermes"
fi

echo "Starting ChironAI server..."
echo "Working directory: $PWD"
echo "Browser will open automatically when the backend is ready."
"$PYTHON" -m webui_backend.rag_proxy
