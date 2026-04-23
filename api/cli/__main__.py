"""
Unified CLI for ChironAI (tmrag).

Usage from project root:
  python -m api.cli start              # start WebUI (Flask)
  python -m api.cli crawl [--dry-run] [--source ID]
  python -m api.cli ingest <markdown_dir> [--collection NAME]
  python -m api.cli proxy              # start RAG proxy (OpenAI-compatible)
  python -m api.cli test                # run pytest tests/
  python -m api.cli test-single [url]  # fetch and convert one Apple doc page

Or: python tmrag.py <command> ...
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys


def _root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _app_py() -> str:
    return os.path.join(_root(), "WebUI", "app.py")


def _run(args: list[str], cwd: str | None = None) -> int:
    cmd = [sys.executable] + args
    return subprocess.run(cmd, cwd=cwd or _root()).returncode


def _default_codex_shim_path() -> str:
    home = os.path.expanduser("~")
    return os.path.join(home, ".chironai", "bin", "codex.cmd")


def _norm_path(p: str) -> str:
    return os.path.normcase(os.path.normpath((p or "").strip().strip('"')))


def _is_launchable_binary(path: str) -> bool:
    """
    Best-effort probe for Windows launchability.
    Returns False for non-Win32 / broken executables (e.g. WinError 193).
    """
    try:
        res = subprocess.run(
            [path, "--version"],
            capture_output=True,
            text=True,
            timeout=6,
        )
        # Any return code means process started; non-zero is still launchable.
        return res.returncode in (0, 1, 2)
    except OSError:
        return False
    except Exception:
        # Timeout/other runtime issues still mean CreateProcess succeeded.
        return True


def _find_real_codex_executable(shim_path: str | None = None) -> str | None:
    """
    Resolve a real codex executable path, skipping the Chiron shim itself.
    This prevents recursion when global `codex` is a wrapper to `chironai launch codex`.
    """
    shim_norm = _norm_path(shim_path or _default_codex_shim_path())
    candidates: list[str] = []
    if os.name == "nt":
        for probe_name in ("codex.cmd", "codex"):
            try:
                out = subprocess.run(
                    ["cmd", "/c", "where", probe_name],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                if out.returncode == 0:
                    candidates.extend([ln.strip() for ln in (out.stdout or "").splitlines() if ln.strip()])
            except Exception:
                pass

    if not candidates:
        found = shutil.which("codex.cmd") or shutil.which("codex")
        if found:
            candidates = [found]

    deduped: list[str] = []
    seen: set[str] = set()
    for c in candidates:
        key = _norm_path(c)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(c)

    for c in deduped:
        if _norm_path(c) != shim_norm and _is_launchable_binary(c):
            return c
    return None


def _resolve_default_codex_model() -> str:
    """
    Resolve default build/model for `chironai launch codex`.
    Priority:
    1) If llm_proxy_builds exists:
       - app_settings.proxy_model when it matches a build id
       - else first build id
    2) Otherwise: empty (caller decides whether to error)
    """
    try:
        from infrastructure.database.settings_repository import get_settings_repository

        repo = get_settings_repository()
        model = (repo.get_app_setting("proxy_model") or "").strip()

        raw_builds = (repo.get_app_setting("llm_proxy_builds") or "").strip()
        if raw_builds:
            try:
                builds = json.loads(raw_builds)
                if isinstance(builds, list):
                    build_ids = [str((b or {}).get("id") or "").strip() for b in builds if isinstance(b, dict)]
                    build_ids = [x for x in build_ids if x]
                    if build_ids:
                        if model and model in build_ids:
                            return model
                        return build_ids[0]
            except json.JSONDecodeError:
                pass
    except Exception:
        pass
    return ""


def _build_codex_proxy_overrides(base_url: str) -> list[str]:
    """
    Runtime Codex config overrides that force custom provider routing through Chiron proxy.
    """
    base = (base_url or "").strip().rstrip("/")
    v1_base = base if base.lower().endswith("/v1") else f"{base}/v1"
    v1_base = f"{v1_base}/"
    provider_id = "chironai-launch"
    return [
        "-c",
        f'model_provider="{provider_id}"',
        "-c",
        # Keep provider shape aligned with Codex Ollama integration semantics.
        f'model_providers.{provider_id}.name="Ollama"',
        "-c",
        f'model_providers.{provider_id}.base_url="{v1_base}"',
        "-c",
        f'model_providers.{provider_id}.wire_api="responses"',
        "-c",
        f'openai_base_url="{v1_base}"',
    ]


def cmd_start(_: argparse.Namespace) -> int:
    app = _app_py()
    if not os.path.isfile(app):
        print("WebUI/app.py not found.", file=sys.stderr)
        return 1
    return _run([app, "start"])


def cmd_crawl(ns: argparse.Namespace) -> int:
    root = _root()
    env = os.environ.copy()
    env["CHIRONAI_PROJECT_ROOT"] = root
    env["CHIRONAI_WEBUI_DIR"] = os.path.join(root, "WebUI")
    _p = os.pathsep.join(
        [
            root,
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
    script = os.path.join(_root(), "WebUI", "app_tester.py")
    if not os.path.isfile(script):
        print("WebUI/app_tester.py not found.", file=sys.stderr)
        return 1
    argv = [script]
    if getattr(ns, "url", None):
        argv.append(ns.url)
    return _run(argv, cwd=os.path.join(_root(), "WebUI"))


def cmd_launch_codex(ns: argparse.Namespace) -> int:
    shim_path = (getattr(ns, "shim_path", None) or "").strip() or _default_codex_shim_path()
    exe = _find_real_codex_executable(shim_path=shim_path)
    if not exe:
        print(
            "A real codex CLI was not found in PATH (only shim or none). "
            "Install with: npm install -g @openai/codex",
            file=sys.stderr,
        )
        return 1

    base_url = (getattr(ns, "base_url", None) or "").strip() or "http://127.0.0.1:8080"
    env_base_url = base_url.rstrip("/")
    if not env_base_url.lower().endswith("/v1"):
        env_base_url = f"{env_base_url}/v1"
    api_key = (getattr(ns, "api_key", None) or "").strip() or "ChironAI"
    working_dir = (getattr(ns, "working_dir", None) or "").strip() or os.getcwd()
    model = (getattr(ns, "model", None) or "").strip()
    if not model:
        model = _resolve_default_codex_model()
    if not model:
        print(
            "No model resolved from llm_proxy_builds. Configure at least one LLM Proxy build id "
            "or pass --model explicitly.",
            file=sys.stderr,
        )
        return 1
    profile = (getattr(ns, "profile", None) or "").strip()

    resolved_dir = os.path.abspath(working_dir)
    if not os.path.isdir(resolved_dir):
        print(f"Project directory not found: {working_dir}", file=sys.stderr)
        return 1

    env = os.environ.copy()
    env["OPENAI_BASE_URL"] = env_base_url
    env["OPENAI_API_BASE"] = env_base_url
    env["OPENAI_API_KEY"] = api_key

    argv = [exe, "--cd", resolved_dir]
    argv.extend(_build_codex_proxy_overrides(base_url))
    if model:
        argv.extend(["--model", model])
    if profile:
        argv.extend(["--profile", profile])

    passthrough = list(getattr(ns, "codex_args", []) or [])
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    argv.extend(passthrough)

    print(f"Launching Codex via ChironAI proxy: {base_url}", file=sys.stderr)
    print(f"Workspace: {resolved_dir}", file=sys.stderr)
    print(f"Model: {model}", file=sys.stderr)
    return subprocess.run(argv, cwd=resolved_dir, env=env).returncode


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="tmrag",
        description="ChironAI CLI: WebUI, crawl, ingest, proxy, tests.",
    )
    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    p_start = sub.add_parser("start", help="Start WebUI (Flask)")
    p_start.set_defaults(_run=cmd_start)

    p_crawl = sub.add_parser("crawl", help="Update markdown store (crawl)")
    p_crawl.add_argument("--dry-run", action="store_true", help="Do not write md/meta")
    p_crawl.add_argument("--source", action="append", dest="sources", metavar="ID", help="Limit to source id")
    p_crawl.set_defaults(_run=cmd_crawl)

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
    p_rag_run.add_argument("--strict-mode", action="store_true", help="Require a verbatim RAG QUOTE from retrieved context")
    p_rag_run.set_defaults(_run=cmd_rag_tests_run)
    p_rag_lint = p_rag_sub.add_parser("lint", help="Lint RAG tests (Expected Concepts hygiene)")
    p_rag_lint.set_defaults(_run=cmd_rag_tests_lint)

    p_launch = sub.add_parser("launch", help="Launch external coding CLIs via ChironAI proxy")
    p_launch_sub = p_launch.add_subparsers(dest="launch_target", metavar="TARGET")
    p_launch_codex = p_launch_sub.add_parser("codex", help="Launch Codex using ChironAI proxy settings")
    p_launch_codex.add_argument(
        "--base-url",
        default=os.environ.get("CHIRON_PROXY_BASE_URL", "http://127.0.0.1:8080"),
        help="Proxy base URL (default: CHIRON_PROXY_BASE_URL or http://127.0.0.1:8080)",
    )
    p_launch_codex.add_argument(
        "--api-key",
        default="ChironAI",
        help="OPENAI_API_KEY value for proxy auth (default: ChironAI)",
    )
    p_launch_codex.add_argument("--model", default=None, help="Optional Codex model/build id")
    p_launch_codex.add_argument("--profile", default=None, help="Optional Codex profile name")
    p_launch_codex.add_argument(
        "--cd",
        dest="working_dir",
        default=os.getcwd(),
        help="Project directory to open in Codex (default: current directory)",
    )
    p_launch_codex.add_argument(
        "codex_args",
        nargs=argparse.REMAINDER,
        help="Extra args forwarded to codex (use '--' before passthrough args)",
    )
    p_launch_codex.add_argument(
        "--shim-path",
        default=os.environ.get("CHIRON_CODEX_SHIM_PATH", _default_codex_shim_path()),
        help="Path to codex shim (used to avoid recursive self-invocation).",
    )
    p_launch_codex.set_defaults(_run=cmd_launch_codex)

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
