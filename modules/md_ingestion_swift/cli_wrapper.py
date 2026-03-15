"""
Python wrapper for the Swift-based markdown ingestion CLI.

This module locates the compiled `swift-md-ingest` binary, invokes it as a subprocess,
and parses the JSON summary into a Python dict compatible with the existing
md_ingestion_service.use_cases output.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Final


def _project_root() -> Path:
    # This file is expected to live under modules/md_ingestion_swift/.
    here = Path(__file__).resolve()
    return here.parents[2]


def _binary_candidates() -> list[Path]:
    root = _project_root()
    bin_dir = root / "bin"
    return [
        bin_dir / "swift-md-ingest",
        bin_dir / "swift-md-ingest.exe",
    ]


def _resolve_binary() -> Path:
    # Allow overriding via environment for flexibility.
    env_path = os.getenv("SWIFT_MD_INGEST_BIN")
    if env_path:
        candidate = Path(env_path)
        if candidate.is_file():
            return candidate
    for cand in _binary_candidates():
        if cand.is_file() and os.access(cand, os.X_OK):
            return cand
    raise FileNotFoundError(
        "swift-md-ingest binary not found. "
        "Ensure it is built and placed in bin/ or set SWIFT_MD_INGEST_BIN."
    )


def run_swift_md_ingest(
    source_path: str,
    source_id: str = "local",
    collection: str = "webcrawl",
    dry_run: bool = False,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    """
    Run the Swift md ingest CLI and return a summary dict:
      {\"files_processed\": int, \"chunks_indexed\": int, \"errors\": [str, ...]}

    Raises RuntimeError on failure.
    """
    binary = _resolve_binary()
    cmd: list[str] = [str(binary), source_path, "--source-id", source_id, "--collection", collection]
    if dry_run:
        cmd.append("--dry-run")

    full_env = os.environ.copy()
    if env:
        full_env.update(env)

    proc = subprocess.run(
        cmd,
        cwd=_project_root(),
        env=full_env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    if not stdout:
        raise RuntimeError(f"swift-md-ingest produced no output. stderr: {stderr}")

    try:
        summary = json.loads(stdout)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse swift-md-ingest JSON output: {e}. Raw: {stdout}") from e

    # Normalize keys to match Python use case output.
    files_processed = int(summary.get("filesProcessed", summary.get("files_processed", 0)))
    chunks_indexed = int(summary.get("chunksIndexed", summary.get("chunks_indexed", 0)))
    errors = summary.get("errors", [])
    if not isinstance(errors, list):
        errors = [str(errors)]

    result: dict[str, Any] = {
        "files_processed": files_processed,
        "chunks_indexed": chunks_indexed,
        "errors": [str(e) for e in errors],
    }

    # Mirror Python CLI behaviour: non-zero exit if there are errors.
    if proc.returncode != 0 and not result["errors"]:
        result["errors"].append(f"swift-md-ingest exited with code {proc.returncode}: {stderr}")

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(
            "Usage: python -m modules.md_ingestion_swift.cli_wrapper <source_path> "
            "[--source-id ID] [--collection NAME] [--dry-run]",
            file=sys.stderr,
        )
        raise SystemExit(1)
    # Very small CLI shim for manual testing.
    src_path = sys.argv[1]
    src_id = "local"
    collection = "webcrawl"
    dry_run_flag = False
    extra = sys.argv[2:]
    it = iter(extra)
    for arg in it:
        if arg == "--source-id":
            try:
                src_id = next(it)
            except StopIteration:
                print("--source-id requires a value", file=sys.stderr)
                raise SystemExit(1)
        elif arg == "--collection":
            try:
                collection = next(it)
            except StopIteration:
                print("--collection requires a value", file=sys.stderr)
                raise SystemExit(1)
        elif arg == "--dry-run":
            dry_run_flag = True
        else:
            print(f"Unknown argument: {arg}", file=sys.stderr)
            raise SystemExit(1)
    summary = run_swift_md_ingest(src_path, source_id=src_id, collection=collection, dry_run=dry_run_flag)
    print(json.dumps(summary, indent=2))

