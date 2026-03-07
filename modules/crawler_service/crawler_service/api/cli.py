"""CLI for crawler. Usage: python -m crawler_service.api.cli crawl --source-id ID (from project root with PYTHONPATH)."""

from __future__ import annotations

import argparse
import sys

from crawler_service.domain.entities import crawl_source_from_dict
from crawler_service.application.use_cases import run_crawl_source
from crawler_service.infrastructure.md_ingestion_http_adapter import MdIngestionHttpAdapter
from crawler_service.infrastructure.playwright_crawler import PlaywrightCrawler


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd")
    crawl_parser = sub.add_parser("crawl")
    crawl_parser.add_argument("--source-id", required=True)
    crawl_parser.add_argument("--url", default="")
    crawl_parser.add_argument("--collection", default="webcrawl")
    args = parser.parse_args()
    if args.cmd != "crawl":
        parser.print_help()
        return 0
    source = crawl_source_from_dict({"id": args.source_id, "url": args.url or args.source_id})
    runner = PlaywrightCrawler()
    client = MdIngestionHttpAdapter()
    try:
        result = run_crawl_source(source, runner, client, args.collection)
    except NotImplementedError as e:
        print(f"Crawler not implemented: {e}", file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
