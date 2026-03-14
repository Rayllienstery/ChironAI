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


def cmd_rag_tests_run(ns: argparse.Namespace) -> int:
    """Run RAG tests from CLI (no Flask)."""
    root = _root()
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from application.rag_tests.loader import get_rag_tests_root, load_all_tests
        from application.rag_tests.runner import run_tests_sync
    except ImportError as e:
        print(f"RAG tests module not available: {e}", file=sys.stderr)
        return 1
    model = (getattr(ns, "model", None) or "").strip()
    if not model:
        print("--model is required", file=sys.stderr)
        return 1
    tests_root = get_rag_tests_root()
    if not tests_root.is_dir():
        print(f"rag_tests root not found: {tests_root}", file=sys.stderr)
        return 1
    tests = load_all_tests(tests_root)
    test_ids = getattr(ns, "test_id", None) or []
    if test_ids:
        by_id = {t["id"]: t for t in tests}
        tests = [by_id[tid] for tid in test_ids if tid in by_id]
    else:
        platform = (getattr(ns, "filter_platform", None) or "").strip()
        framework = (getattr(ns, "filter_framework", None) or "").strip()
        difficulty = (getattr(ns, "filter_difficulty", None) or "").strip()
        if platform:
            tests = [t for t in tests if (t.get("platform") or "") == platform]
        if framework:
            tests = [t for t in tests if (t.get("framework") or "") == framework]
        if difficulty:
            tests = [t for t in tests if (t.get("difficulty") or "") == difficulty]
    if not tests:
        print("No tests to run.", file=sys.stderr)
        return 1

    def on_progress(current: int, total: int, name: str) -> None:
        print(f"  [{current}/{total}] {name}", file=sys.stderr)

    results = run_tests_sync(tests, model, on_progress=on_progress)
    passed = sum(1 for r in results if r.get("status") == "PASS")
    failed = len(results) - passed
    for r in results:
        status = r.get("status", "?")
        name = r.get("test_name") or r.get("test_id", "?")
        print(f"  {status}: {name}")
    print(f"\nPassed: {passed}, Failed: {failed}, Total: {len(results)}")
    return 0 if failed == 0 else 1


def cmd_rag_tests_lint(_: argparse.Namespace) -> int:
    """Lint RAG tests for multi-concept Expected Concepts."""
    root = _root()
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from application.rag_tests.loader import get_rag_tests_root, load_all_tests
        from application.rag_tests.lint import lint_expected_concepts, format_issues_text
    except ImportError as e:
        print(f"RAG tests module not available: {e}", file=sys.stderr)
        return 1

    tests_root = get_rag_tests_root()
    if not tests_root.is_dir():
        print(f"rag_tests root not found: {tests_root}", file=sys.stderr)
        return 1

    tests = load_all_tests(tests_root)
    issues = lint_expected_concepts(tests)
    print(format_issues_text(issues))
    # Non-zero exit if any issues found so that CI can fail on bad tests.
    return 0 if not issues else 1


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

    p_rag = sub.add_parser("rag-tests", help="RAG tests (run from CLI)")
    p_rag_sub = p_rag.add_subparsers(dest="rag_command", metavar="SUBCOMMAND")
    p_rag_run = p_rag_sub.add_parser("run", help="Run RAG tests (no WebUI)")
    p_rag_run.add_argument("--model", required=True, help="Ollama model to use")
    p_rag_run.add_argument("--filter-platform", dest="filter_platform", help="Filter tests by platform")
    p_rag_run.add_argument("--filter-framework", dest="filter_framework", help="Filter tests by framework")
    p_rag_run.add_argument("--filter-difficulty", dest="filter_difficulty", help="Filter tests by difficulty")
    p_rag_run.add_argument("--test-id", dest="test_id", action="append", default=[], metavar="ID", help="Run specific test(s) by id (repeatable)")
    p_rag_run.set_defaults(_run=cmd_rag_tests_run)
    p_rag_lint = p_rag_sub.add_parser("lint", help="Lint RAG tests (Expected Concepts hygiene)")
    p_rag_lint.set_defaults(_run=cmd_rag_tests_lint)

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
