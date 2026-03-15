"""
CLI to ingest external docs (e.g. TMArchitecture) into a Qdrant collection.

Usage (from repo root, with modules/external_docs_rag on PYTHONPATH):
  python -m external_docs_rag.api.cli ingest tm_architecture
  python -m external_docs_rag.api.cli ingest --list
"""

from __future__ import annotations

import argparse
import os
import sys


def _ensure_path() -> None:
    mod_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if mod_dir not in sys.path:
        sys.path.insert(0, mod_dir)


def cmd_list(config_path: str | None) -> int:
    _ensure_path()
    from external_docs_rag.config_loader import load_external_sources
    sources = load_external_sources(config_path)
    if not sources:
        print("No external sources in config. Check config/sources.yaml.")
        return 0
    for s in sources:
        print(f"  {s.id}: {s.base_url} -> collection {s.collection_name} (paths: {len(s.paths)})")
    return 0


def cmd_ingest(source_id: str, config_path: str | None, qdrant_url: str | None) -> int:
    _ensure_path()
    from external_docs_rag.config_loader import load_external_sources
    from external_docs_rag.application.use_cases import ingest_source_to_collection
    from external_docs_rag.infrastructure import HttpFetchClient, QdrantChunkSink
    from external_docs_rag.infrastructure.ollama_embed_adapter import OllamaEmbedAdapter

    sources = load_external_sources(config_path)
    source = next((s for s in sources if s.id == source_id), None)
    if not source:
        print(f"Source '{source_id}' not found. Use --list to see available sources.")
        return 1
    fetch_client = HttpFetchClient()
    sink = QdrantChunkSink(base_url=qdrant_url or os.getenv("QDRANT_URL", "http://localhost:6333"))
    embed = OllamaEmbedAdapter()
    print(f"Ingesting {source.id} from {source.base_url} into collection '{source.collection_name}'...")
    result = ingest_source_to_collection(source, fetch_client, sink, embed)
    print(f"  Documents fetched: {result.documents_fetched}")
    print(f"  Chunks indexed: {result.chunks_indexed}")
    if result.errors:
        for e in result.errors:
            print(f"  Error: {e}")
    return 0 if not result.errors else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="External docs RAG: ingest from URLs into Qdrant.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_ingest = sub.add_parser("ingest", help="Ingest a source by id")
    p_ingest.add_argument("source_id", nargs="?", default=None, help="Source id (e.g. tm_architecture)")
    p_ingest.add_argument("--list", action="store_true", help="List configured sources and exit")
    p_ingest.add_argument("--config", default=None, help="Path to sources.yaml")
    p_ingest.add_argument("--qdrant-url", default=None, help="Qdrant base URL")
    args = parser.parse_args()
    if args.command == "ingest":
        if getattr(args, "list", False):
            return cmd_list(getattr(args, "config", None))
        sid = getattr(args, "source_id", None)
        if not sid:
            print("Usage: ingest <source_id> (e.g. tm_architecture) or ingest --list")
            return 1
        return cmd_ingest(sid, getattr(args, "config", None), getattr(args, "qdrant_url", None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
