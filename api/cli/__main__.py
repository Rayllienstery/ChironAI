"""
Unified CLI for TMRagFetcher (tmrag).

Usage from project root:
  python -m api.cli start              # start WebUI (Flask)
  python -m api.cli crawl [--dry-run] [--source ID]
  python -m api.cli index [--dry-run] [--source ID] [--reindex-source ID]
  python -m api.cli rebuild [--dry-run]
  python -m api.cli update [--dry-run] [--source ID]
  python -m api.cli ingest <markdown_dir> [--collection NAME]
  python -m api.cli proxy              # start RAG proxy (OpenAI-compatible)
  python -m api.cli test                # run pytest tests/
  python -m api.cli test-single [url]  # fetch and convert one Apple doc page

Or: python tmrag.py <command> ...
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _app_py() -> str:
    return os.path.join(_root(), "WebUI", "app.py")


def _run(args: list[str], cwd: str | None = None) -> int:
    cmd = [sys.executable] + args
    return subprocess.run(cmd, cwd=cwd or _root()).returncode


def cmd_start(_: argparse.Namespace) -> int:
    app = _app_py()
    if not os.path.isfile(app):
        print("WebUI/app.py not found.", file=sys.stderr)
        return 1
    return _run([app, "start"])


def cmd_crawl(ns: argparse.Namespace) -> int:
    app = _app_py()
    if not os.path.isfile(app):
        print("WebUI/app.py not found.", file=sys.stderr)
        return 1
    argv = [app, "crawl"]
    if getattr(ns, "dry_run", False):
        argv.append("--dry-run")
    for s in getattr(ns, "sources", None) or []:
        argv.extend(["--source", s])
    return _run(argv)


def cmd_index(ns: argparse.Namespace) -> int:
    app = _app_py()
    if not os.path.isfile(app):
        print("WebUI/app.py not found.", file=sys.stderr)
        return 1
    argv = [app, "index"]
    if getattr(ns, "dry_run", False):
        argv.append("--dry-run")
    for s in getattr(ns, "sources", None) or []:
        argv.extend(["--source", s])
    if getattr(ns, "reindex_source", None):
        argv.extend(["--reindex-source", ns.reindex_source])
    return _run(argv)


def cmd_rebuild(ns: argparse.Namespace) -> int:
    app = _app_py()
    if not os.path.isfile(app):
        print("WebUI/app.py not found.", file=sys.stderr)
        return 1
    argv = [app, "rebuild"]
    if getattr(ns, "dry_run", False):
        argv.append("--dry-run")
    return _run(argv)


def cmd_update(ns: argparse.Namespace) -> int:
    app = _app_py()
    if not os.path.isfile(app):
        print("WebUI/app.py not found.", file=sys.stderr)
        return 1
    argv = [app, "update"]
    if getattr(ns, "dry_run", False):
        argv.append("--dry-run")
    for s in getattr(ns, "sources", None) or []:
        argv.extend(["--source", s])
    if getattr(ns, "reindex_source", None):
        argv.extend(["--reindex-source", ns.reindex_source])
    return _run(argv)


def cmd_ingest(ns: argparse.Namespace) -> int:
    script = os.path.join(_root(), "WebUI", "ingest_markdown_local.py")
    if not os.path.isfile(script):
        print("WebUI/ingest_markdown_local.py not found.", file=sys.stderr)
        return 1
    argv = [script, ns.markdown_dir]
    if getattr(ns, "collection", None):
        argv.extend(["--collection", ns.collection])
    return _run(argv)


def cmd_proxy(_: argparse.Namespace) -> int:
    script = os.path.join(_root(), "WebUI", "rag_proxy.py")
    if not os.path.isfile(script):
        print("WebUI/rag_proxy.py not found.", file=sys.stderr)
        return 1
    return _run([script])


def cmd_test(_: argparse.Namespace) -> int:
    tests_dir = os.path.join(_root(), "tests")
    if not os.path.isdir(tests_dir):
        print("tests/ not found.", file=sys.stderr)
        return 1
    return _run(["-m", "pytest", "tests/"])


def cmd_test_single(ns: argparse.Namespace) -> int:
    script = os.path.join(_root(), "WebUI", "app_tester.py")
    if not os.path.isfile(script):
        print("WebUI/app_tester.py not found.", file=sys.stderr)
        return 1
    argv = [script]
    if getattr(ns, "url", None):
        argv.append(ns.url)
    return _run(argv, cwd=os.path.join(_root(), "WebUI"))


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tmrag",
        description="TMRagFetcher CLI: WebUI, crawl, index, ingest, proxy, tests.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_start = sub.add_parser("start", help="Start WebUI (Flask)")
    p_start.set_defaults(_run=cmd_start)

    p_crawl = sub.add_parser("crawl", help="Update markdown store (crawl)")
    p_crawl.add_argument("--dry-run", action="store_true", help="Do not write md/meta")
    p_crawl.add_argument("--source", action="append", dest="sources", metavar="ID", help="Limit to source id")
    p_crawl.set_defaults(_run=cmd_crawl)

    p_index = sub.add_parser("index", help="Index dirty pages to Qdrant")
    p_index.add_argument("--dry-run", action="store_true", help="Do not upsert")
    p_index.add_argument("--source", action="append", dest="sources", metavar="ID", help="Limit to source id")
    p_index.add_argument("--reindex-source", metavar="ID", help="Re-index all pages of this source")
    p_index.set_defaults(_run=cmd_index)

    p_rebuild = sub.add_parser("rebuild", help="Drop collection and full re-index")
    p_rebuild.add_argument("--dry-run", action="store_true", help="Do not delete/index")
    p_rebuild.set_defaults(_run=cmd_rebuild)

    p_update = sub.add_parser("update", help="Crawl then index (full update)")
    p_update.add_argument("--dry-run", action="store_true", help="Do not write")
    p_update.add_argument("--source", action="append", dest="sources", metavar="ID", help="Limit to source id")
    p_update.add_argument("--reindex-source", metavar="ID", help="(index step) Re-index all pages of this source")
    p_update.set_defaults(_run=cmd_update)

    p_ingest = sub.add_parser("ingest", help="Ingest local markdown folder into Qdrant")
    p_ingest.add_argument("markdown_dir", help="Path to markdown folder")
    p_ingest.add_argument("--collection", help="Qdrant collection name (default from folder name)")
    p_ingest.set_defaults(_run=cmd_ingest)

    p_proxy = sub.add_parser("proxy", help="Start RAG proxy (OpenAI-compatible, for Zed etc.)")
    p_proxy.set_defaults(_run=cmd_proxy)

    p_test = sub.add_parser("test", help="Run pytest tests/")
    p_test.set_defaults(_run=cmd_test)

    p_ts = sub.add_parser("test-single", help="Fetch and convert one Apple doc page (app_tester)")
    p_ts.add_argument("url", nargs="?", default=None, help="Page URL (default: SwiftUI View)")
    p_ts.set_defaults(_run=cmd_test_single)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    run_fn = getattr(args, "_run", None)
    if run_fn is None:
        parser.print_help()
        sys.exit(0)
    sys.exit(run_fn(args))


if __name__ == "__main__":
    main()
