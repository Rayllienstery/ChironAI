"""
Unified CLI for ChironAI (tmrag).

Usage from project root:
  python -m api.cli start              # start WebUI (Flask)
  python -m api.cli crawl [--dry-run] [--source ID]
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
    return os.path.join(_root(), "CoreModules", "WebUIBackend", "webui_backend", "app.py")


def _webui_backend_root() -> str:
    return os.path.join(_root(), "CoreModules", "WebUIBackend")


def _module_env() -> dict[str, str]:
    env = os.environ.copy()
    paths = [_root(), _webui_backend_root()]
    existing = env.get("PYTHONPATH")
    if existing:
        paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    return env


def _run(args: list[str], cwd: str | None = None, env: dict[str, str] | None = None) -> int:
    cmd = [sys.executable] + args
    return subprocess.run(cmd, cwd=cwd or _root(), env=env).returncode


def cmd_start(_: argparse.Namespace) -> int:
    if not os.path.isfile(_app_py()):
        print("webui_backend.app not found.", file=sys.stderr)
        return 1
    return _run(["-m", "webui_backend.app", "start"], env=_module_env())


def cmd_crawl(ns: argparse.Namespace) -> int:
    root = _root()
    env = os.environ.copy()
    env["CHIRONAI_PROJECT_ROOT"] = root
    env["CHIRONAI_WEBUI_DIR"] = os.path.join(root, "WebUI")
    _p = os.pathsep.join(
        [
            root,
            os.path.join(root, "CoreModules", "WebUIBackend"),
            os.path.join(root, "modules", "crawler_service"),
            os.path.join(root, "modules", "html_md"),
        ]
    )
    env["PYTHONPATH"] = _p + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    argv = [sys.executable, "-m", "crawler_service.api.cli", "crawl"]
    if getattr(ns, "dry_run", False):
        argv.append("--dry-run")
    for s in getattr(ns, "sources", None) or []:
        argv.extend(["--source", s])
    return subprocess.run(argv, cwd=root, env=env).returncode


def cmd_proxy(_: argparse.Namespace) -> int:
    script = os.path.join(_webui_backend_root(), "webui_backend", "rag_proxy.py")
    if not os.path.isfile(script):
        print("webui_backend.rag_proxy not found.", file=sys.stderr)
        return 1
    return _run(["-m", "webui_backend.rag_proxy"], env=_module_env())


def cmd_test(_: argparse.Namespace) -> int:
    tests_dir = os.path.join(_root(), "tests")
    if not os.path.isdir(tests_dir):
        print("tests/ not found.", file=sys.stderr)
        return 1
    return _run(["-m", "pytest", "tests/"])


def _strip_dashdash(args: list[str]) -> list[str]:
    if args and args[0] == "--":
        return args[1:]
    return args


def _pick_codex_build(builds: list[dict]) -> dict | None:
    print("Select ChironAI IDE build for Codex:")
    for index, build in enumerate(builds, start=1):
        bid = str(build.get("id") or "")
        title = str(build.get("display_name") or bid)
        model = str(build.get("model") or build.get("ollama_model") or "")
        provider = str(build.get("provider_id") or "")
        suffix = f" ({provider}/{model})" if provider or model else ""
        print(f"  {index}. {title} [{bid}]{suffix}")
    try:
        raw = input("Build number: ").strip()
    except EOFError:
        return None
    try:
        selected = int(raw)
    except ValueError:
        return None
    if selected < 1 or selected > len(builds):
        return None
    return builds[selected - 1]


def cmd_codex(ns: argparse.Namespace) -> int:
    root = _root()
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        from application.codex_launcher import (
            CodexLauncherError,
            build_codex_argv,
            build_codex_env,
            build_command_preview,
            check_proxy_reachable,
            ide_builds,
            load_builds,
            proxy_base_url,
            require_codex_installed,
            reveal_existing_proxy_key,
            selected_ide_build,
            write_codex_profile,
        )
        from config import get_server_port
        from infrastructure.database import get_settings_repository
    except ImportError as e:
        print(f"Codex launcher unavailable: {e}", file=sys.stderr)
        return 1

    try:
        require_codex_installed()
        settings_repo = get_settings_repository()
        api_key = reveal_existing_proxy_key(settings_repo)
        base_url = proxy_base_url(get_server_port())
        check_proxy_reachable(base_url, api_key)
        builds = ide_builds(load_builds(settings_repo))
        if not builds:
            raise CodexLauncherError("No IDE-enabled builds found. Enable IDE mode in LLM Proxy Builds -> Agent Proxy Mode.")
        requested_model = str(getattr(ns, "model", "") or "").strip()
        if requested_model:
            build = selected_ide_build(builds, requested_model)
        else:
            build = _pick_codex_build(builds)
            if build is None:
                raise CodexLauncherError("No build selected")
        build_id = str(build.get("id") or "").strip()
        config_path = write_codex_profile(base_url, build=build, builds=builds)
        extra_args = _strip_dashdash(list(getattr(ns, "extra_args", None) or []))
        argv = build_codex_argv(build_id, extra_args)
        print(f"Configured Codex profile at {config_path}")
        print(f"Command: {build_command_preview(build_id)}")
        if bool(getattr(ns, "config", False)):
            return 0
        return subprocess.run(argv, cwd=os.getcwd(), env=build_codex_env(api_key)).returncode
    except CodexLauncherError as e:
        print(str(e), file=sys.stderr)
        return 1


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

    results = run_tests_sync(tests, model, strict_mode=bool(getattr(ns, "strict_mode", False)), on_progress=on_progress)
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
    script = os.path.join(_webui_backend_root(), "webui_backend", "app_tester.py")
    if not os.path.isfile(script):
        print("webui_backend.app_tester not found.", file=sys.stderr)
        return 1
    argv = ["-m", "webui_backend.app_tester"]
    if getattr(ns, "url", None):
        argv.append(ns.url)
    return _run(argv, env=_module_env())


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="chironai",
        description="ChironAI CLI: WebUI, crawl, proxy, tests.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_start = sub.add_parser("start", help="Start WebUI (Flask)")
    p_start.set_defaults(_run=cmd_start)

    p_crawl = sub.add_parser("crawl", help="Update markdown store (crawl)")
    p_crawl.add_argument("--dry-run", action="store_true", help="Do not write md/meta")
    p_crawl.add_argument("--source", action="append", dest="sources", metavar="ID", help="Limit to source id")
    p_crawl.set_defaults(_run=cmd_crawl)

    p_proxy = sub.add_parser("proxy", help="Start RAG proxy (OpenAI-compatible, for Zed etc.)")
    p_proxy.set_defaults(_run=cmd_proxy)

    p_codex = sub.add_parser("codex", help="Launch Codex with a ChironAI IDE build")
    p_codex.add_argument("--model", help="IDE-enabled LLM Proxy build id to use")
    p_codex.add_argument("--config", action="store_true", help="Configure Codex profile without launching")
    p_codex.add_argument("extra_args", nargs=argparse.REMAINDER, help="Arguments after -- are passed to Codex")
    p_codex.set_defaults(_run=cmd_codex)

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
    p_rag_run.add_argument("--strict-mode", action="store_true", help="Require a verbatim RAG QUOTE from retrieved context")
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
