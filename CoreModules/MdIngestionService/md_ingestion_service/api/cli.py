"""
CLI for local markdown ingestion.

Usage (from project root): PYTHONPATH=. python -m md_ingestion_service.api.cli <source_path> [--source-id ID] [--collection NAME]
"""

from __future__ import annotations

import argparse
import sys

from md_ingestion_service.application.use_cases import ingest_local_markdown
from md_ingestion_service.infrastructure.fs_source_store import FsSourceStore
from md_ingestion_service.infrastructure.rag_sink_http import RagSinkHttp


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest local markdown into RAG")
    parser.add_argument("source_path", help="Directory containing .md files")
    parser.add_argument("--source-id", default="local", help="Source identifier")
    parser.add_argument("--collection", default="webcrawl", help="Target RAG collection name")
    parser.add_argument("--dry-run", action="store_true", help="Only count files/chunks, do not write")
    args = parser.parse_args()

    source_store = FsSourceStore()
    if args.dry_run:
        from md_ingestion_service.application.use_cases import dry_run_ingest
        from md_ingestion_service.domain.services.filtering import default_filter_rule

        result = dry_run_ingest(args.source_id, args.source_path, source_store, default_filter_rule())
        print(
            f"Paths scanned: {result['paths_scanned']}, "
            f"files_processed: {result['files_processed']}, "
            f"total_chunks: {result['total_chunks']}"
        )
        return 0

    output_sink = RagSinkHttp()
    result = ingest_local_markdown(
        args.source_id,
        args.source_path,
        source_store,
        output_sink,
        args.collection,
    )
    print(f"files_processed={result['files_processed']}, chunks_indexed={result['chunks_indexed']}")
    if result["errors"]:
        for e in result["errors"]:
            print(f"Error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
