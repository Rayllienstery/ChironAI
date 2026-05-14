"""CLI for standalone rag_service runtime operations."""

from __future__ import annotations

import argparse
import json
import sys

from rag_service.runtime import RagRuntime


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="rag-service", description="Standalone RAG Beta 0.1 runtime")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("health", help="Show health for Ollama/Qdrant runtime dependencies")
    sub.add_parser("start-qdrant", help="Pull/start Qdrant container")
    sub.add_parser("stop-qdrant", help="Stop Qdrant container")
    p_all = sub.add_parser("start-deps", help="Start selected runtime dependencies")
    p_all.add_argument(
        "--services",
        default="qdrant",
        help="Comma-separated: docker,qdrant (ollama: use ChironAI Ollama tab)",
    )
    args = parser.parse_args(argv)
    rt = RagRuntime()

    if args.command == "health":
        print(json.dumps(rt.health(), indent=2))
        return 0
    if args.command == "start-qdrant":
        ok, msg = rt.start_qdrant()
        print(msg)
        return 0 if ok else 1
    if args.command == "stop-qdrant":
        ok, msg = rt.stop_qdrant()
        print(msg)
        return 0 if ok else 1
    if args.command == "start-deps":
        services = [x.strip() for x in str(args.services).split(",") if x.strip()]
        print(json.dumps(rt.start_dependencies(services), indent=2))
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
