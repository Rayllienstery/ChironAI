"""CLI: crawl configured sources into WebUI/rag_sources."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from crawler_service.application.crawl_runner import build_crawl_host, run_crawl_all_sources


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ChironAI crawl: update local markdown store under WebUI/rag_sources.",
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["crawl"],
        default="crawl",
        help="crawl: update markdown store from configured sources",
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="SOURCE_ID",
        help="Limit to source id (repeatable). Omit to crawl all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="crawl_all",
        help="Crawl all configured sources (same as omitting --source).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Crawl without writing md/meta.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Repository root (default: CHIRONAI_PROJECT_ROOT or cwd).",
    )
    parser.add_argument(
        "--webui-dir",
        type=Path,
        default=None,
        help="WebUI directory (default: CHIRONAI_WEBUI_DIR or <project-root>/WebUI).",
    )
    args = parser.parse_args()

    project_root = (args.project_root or Path(os.environ.get("CHIRONAI_PROJECT_ROOT", "").strip() or ".")).resolve()
    webui_dir = args.webui_dir
    if webui_dir is not None:
        webui_dir = webui_dir.resolve()

    pr = str(project_root)
    if pr not in sys.path:
        sys.path.insert(0, pr)

    host = build_crawl_host(project_root=project_root, webui_dir=webui_dir, log=print, is_cli=True)
    source_list = None if getattr(args, "crawl_all", False) else (args.sources if args.sources else None)

    if args.command == "crawl":
        run_crawl_all_sources(host, source_filter=source_list, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
