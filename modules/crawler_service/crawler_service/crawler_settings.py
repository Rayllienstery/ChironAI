"""Load framework allowlist / excluded paths from config/crawler.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from crawler_service.constants import DEFAULT_EXCLUDED_PATH_SUBSTRINGS, DEFAULT_FRAMEWORK_ROOT_PREFIXES


@dataclass(frozen=True)
class CrawlerRuntimeConfig:
    framework_root_prefixes: list[str]
    excluded_path_substrings: list[str]


def load_crawler_runtime_config(project_root: Path) -> CrawlerRuntimeConfig:
    config_path = project_root / "config" / "crawler.yaml"
    if not config_path.is_file():
        return CrawlerRuntimeConfig(
            framework_root_prefixes=list(DEFAULT_FRAMEWORK_ROOT_PREFIXES),
            excluded_path_substrings=list(DEFAULT_EXCLUDED_PATH_SUBSTRINGS),
        )
    try:
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        crawler = data.get("crawler") or {}
        prefixes = crawler.get("framework_root_prefixes")
        excluded = crawler.get("excluded_path_substrings")
        return CrawlerRuntimeConfig(
            framework_root_prefixes=list(prefixes)
            if isinstance(prefixes, list)
            else list(DEFAULT_FRAMEWORK_ROOT_PREFIXES),
            excluded_path_substrings=list(excluded)
            if isinstance(excluded, list)
            else list(DEFAULT_EXCLUDED_PATH_SUBSTRINGS),
        )
    except Exception:
        return CrawlerRuntimeConfig(
            framework_root_prefixes=list(DEFAULT_FRAMEWORK_ROOT_PREFIXES),
            excluded_path_substrings=list(DEFAULT_EXCLUDED_PATH_SUBSTRINGS),
        )
