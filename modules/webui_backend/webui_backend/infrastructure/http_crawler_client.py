"""CrawlerClient implementation via HTTP to crawler_service."""

from __future__ import annotations

import os
from typing import Any

import requests

CRAWLER_SERVICE_URL = os.getenv("CRAWLER_SERVICE_URL", "http://localhost:5003")


class HttpCrawlerClient:
    def __init__(self, base_url: str | None = None) -> None:
        self._base = (base_url or CRAWLER_SERVICE_URL).rstrip("/")

    def list_sources(self) -> dict[str, Any]:
        r = requests.get(f"{self._base}/crawl/sources", timeout=10)
        r.raise_for_status()
        return r.json()

    def start_crawl(self, source_id: str) -> dict[str, Any]:
        r = requests.post(f"{self._base}/crawl/start", json={"source_id": source_id}, timeout=30)
        r.raise_for_status()
        return r.json()


__all__ = ["HttpCrawlerClient"]
