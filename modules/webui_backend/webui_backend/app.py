"""
WebUI Flask host: registers shared API blueprint and crawl entrypoints.

Crawl logic lives in ``crawler_service`` (install: ``pip install -e modules/crawler_service``).
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
import time

from flask import Flask

from webui_backend.paths import project_root, webui_data_dir

_ROOT_DIR = str(project_root())
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

_CRAWLER_ROOT = os.path.join(_ROOT_DIR, "modules", "crawler_service")
if _CRAWLER_ROOT not in sys.path:
    sys.path.insert(0, _CRAWLER_ROOT)
_HTML_MD_ROOT = os.path.join(_ROOT_DIR, "modules", "html_md")
if _HTML_MD_ROOT not in sys.path:
    sys.path.insert(0, _HTML_MD_ROOT)
for _extra in (
    "CoreModules/ErrorManager",
    "CoreModules/RagService",
    "CoreModules/MdIngestionService",
    "modules/extensions_backend",
):
    _p = os.path.join(_ROOT_DIR, _extra)
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

from crawler_service.application.crawl_runner import (  # noqa: E402
    build_crawl_host,
    crawl_source as _crawl_source_impl,
    page_filename_for_url,
    run_crawl_all_sources as _run_crawl_all_sources_impl,
)
from crawler_service.sources_io import load_sources, save_sources  # noqa: E402

app = Flask(__name__)

from api.http.webui_routes import webui_bp  # noqa: E402
from core.openapi import register_openapi_routes  # noqa: E402

app.register_blueprint(webui_bp)
register_openapi_routes(app)

log_queue: list[str] = []
stop_flag = False
id_counter = 1

IS_CLI = False

BASE_DIR = str(webui_data_dir())
RAG_SOURCES_DIR = os.path.join(BASE_DIR, "rag_sources")
PROJECT_ROOT = project_root()

SOURCES = load_sources(PROJECT_ROOT)

# app_tester and legacy scripts
_page_filename_for_url = page_filename_for_url


def _save_sources_to_yaml(sources: list[dict]) -> bool:
    return save_sources(PROJECT_ROOT, sources)


def log(message: str) -> None:
    print(message)
    if not IS_CLI:
        log_queue.append(message)


def cli_progress(prefix: str, current: int, total: int) -> None:
    if not IS_CLI or total <= 0:
        return
    percent = int(current * 100 / total)
    msg = f"{prefix}: {current}/{total} ({percent}%)"
    print("\r" + msg.ljust(80), end="", flush=True)
    if current >= total:
        print()


def event_stream():
    global stop_flag
    idx = 0
    while not stop_flag or idx < len(log_queue):
        if idx < len(log_queue):
            data = log_queue[idx]
            idx += 1
            yield f"data: {data}\n\n"
        else:
            time.sleep(0.5)


def _crawl_host():
    return build_crawl_host(
        project_root=PROJECT_ROOT,
        webui_dir=webui_data_dir(),
        log=log,
        is_cli=IS_CLI,
    )


def crawl_source(source: dict, dry_run: bool = False) -> None:
    _crawl_source_impl(_crawl_host(), source, dry_run=dry_run)


def run_crawl_all_sources(
    source_filter: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    _run_crawl_all_sources_impl(
        _crawl_host(),
        source_filter=source_filter,
        dry_run=dry_run,
        sources_override=SOURCES,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="WebUI server or crawl: update local markdown store under rag_sources.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["start", "crawl"],
        help="start: run WebUI (Flask); crawl: update markdown store from configured sources",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="SOURCE_ID",
        help="Limit to source id (e.g. apple_documentation). Can be repeated.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="crawl_all",
        help="Crawl all configured sources (same as omitting --source).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Crawl without writing md/meta.")
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "start":
        from config import get_webui_port

        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        port = get_webui_port()
        app.run(host="0.0.0.0", port=port, threaded=True)
        sys.exit(0)

    source_list = None if getattr(args, "crawl_all", False) else (args.sources if args.sources else None)
    if args.command == "crawl":
        host = build_crawl_host(
            project_root=PROJECT_ROOT,
            webui_dir=webui_data_dir(),
            log=print,
            is_cli=True,
        )
        _run_crawl_all_sources_impl(
            host,
            source_filter=source_list,
            dry_run=args.dry_run,
            sources_override=SOURCES,
        )
    else:
        parser.print_help()
        sys.exit(1)
