"""Orchestrate WWDC and Playwright crawls into WebUI/rag_sources."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests
from html_md.convert import html_to_markdown

from crawler_service.constants import SWIFT_BOOK_ALLOWED_SLUGS, SWIFT_BOOK_EXCLUDED_SLUGS
from crawler_service.crawler_settings import CrawlerRuntimeConfig, load_crawler_runtime_config
from crawler_service.domain.wwdc_transcript import (
    extract_wwdc_session_id_from_url,
    flatten_wwdc_transcript_json,
    parse_wwdc_event_year,
    wwdc_segments_to_markdown,
)
from crawler_service.infrastructure.apple_fetch_thread import fetch_apple_doc_raw_safe
from crawler_service.infrastructure.crawl_result import CrawlResult
from crawler_service.infrastructure.playwright_deep_crawl import _HAS_PLAYWRIGHT, run_async_crawl_playwright
from crawler_service.paths import default_project_root, rag_sources_dir, resolve_webui_dir
from crawler_service.sources_io import load_sources

try:
    from modules.md_indexer import get_active_pipeline_name, run_pipeline as run_md_indexer_pipeline
except ImportError:
    get_active_pipeline_name = None
    run_md_indexer_pipeline = None  # type: ignore[assignment,misc]

try:
    from domain.services.markdown_meta import parse_and_strip_meta_block
except ImportError:
    parse_and_strip_meta_block = None  # type: ignore[assignment,misc]


def _ensure_project_on_path(project_root: Path) -> None:
    s = str(project_root.resolve())
    if s not in sys.path:
        sys.path.insert(0, s)


@dataclass
class CrawlHost:
    project_root: Path
    webui_dir: Path
    log: Callable[[str], None]
    is_cli: bool
    runtime: CrawlerRuntimeConfig

    @property
    def rag_dir(self) -> Path:
        return rag_sources_dir(self.webui_dir)


def _ensure_dir(path: str | Path) -> None:
    os.makedirs(path, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "page"


def page_filename_for_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        path = (parsed.path or "").strip("/")
        if not path:
            base = "index"
        else:
            segments = [s for s in path.split("/") if s]
            base = segments[-1]
        base = _slugify(base)
    except Exception:
        base = "page"
    h = _sha256(url)[:8]
    return f"{base}-{h}.md"


def _source_dirs(host: CrawlHost, source_id: str) -> tuple[str, str]:
    root = os.path.join(str(host.rag_dir), source_id)
    pages = os.path.join(root, "pages")
    return root, pages


def _meta_path(host: CrawlHost, source_id: str) -> str:
    root, _ = _source_dirs(host, source_id)
    return os.path.join(root, "meta.json")


def _load_meta(host: CrawlHost, source_id: str, source_url: str) -> dict[str, Any]:
    path = _meta_path(host, source_id)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("source_id", source_id)
            data.setdefault("source_url", source_url)
            data.setdefault("hash_algo", "sha256")
            data.setdefault("pages", {})
            return data
        except Exception as e:
            host.log(f"WARNING: Failed to read meta.json for {source_id}: {e}")
    return {
        "source_id": source_id,
        "source_url": source_url,
        "last_crawled": None,
        "hash_algo": "sha256",
        "pages": {},
    }


def _save_meta(host: CrawlHost, source_id: str, meta: dict[str, Any]) -> None:
    root, _ = _source_dirs(host, source_id)
    _ensure_dir(root)
    path = _meta_path(host, source_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        host.log(f" Failed to write meta.json for {source_id}: {e}")


def apply_markdown_cleanup_pipeline(md: str) -> tuple[dict[str, Any], str]:
    if run_md_indexer_pipeline is not None and get_active_pipeline_name is not None:
        return run_md_indexer_pipeline(get_active_pipeline_name(), md)
    if parse_and_strip_meta_block is not None:
        return parse_and_strip_meta_block(md)
    return ({}, md)


def crawl_wwdc_transcripts_source(host: CrawlHost, source: dict[str, Any], dry_run: bool = False) -> None:
    source_id = source["id"]
    extra = source.get("extra") or {}
    tsv_url = extra.get(
        "tsv_url",
        "https://gist.githubusercontent.com/elkraneo/6015e04c81dd227dd9974a2ec9d89cff/raw/WWDC-Transcripts-2014-2024-ENG.tsv",
    )
    min_year = int(extra.get("min_year", 2019))

    host.log(
        f"[source={source_id}] Fetching WWDC transcript index from TSV: {tsv_url} "
        + (f"(min_year={min_year})" if min_year else "")
        + (" [dry-run]" if dry_run else "")
    )

    try:
        resp = requests.get(tsv_url, timeout=60)
        resp.raise_for_status()
        tsv_text = resp.text
    except Exception as e:
        host.log(f"ERROR: [source={source_id}] Failed to download TSV index: {e}")
        return

    start_url = source.get("url", tsv_url)
    meta = _load_meta(host, source_id, start_url)
    pages_meta: dict[str, Any] = meta.get("pages", {})
    _, pages_dir = _source_dirs(host, source_id)
    if not dry_run:
        _ensure_dir(pages_dir)

    reader = csv.DictReader(tsv_text.splitlines(), delimiter="\t")
    rows: list[dict[str, str]] = []
    for row in reader:
        event = (row.get("Event") or "").strip()
        link = (row.get("Link") or "").strip()
        title = (row.get("Transcript Name") or "").strip()
        if not event or not link or not title:
            continue
        year = parse_wwdc_event_year(event)
        if year is None or (min_year and year < min_year):
            continue
        rows.append({"event": event, "year": str(year), "link": link, "title": title})

    if not rows:
        host.log(f"[source={source_id}] No WWDC rows matched filter (min_year={min_year}); nothing to do.")
        return

    host.log(f"[source={source_id}] {len(rows)} WWDC transcript(s) to process from TSV.")

    changed_count = 0

    for idx, row in enumerate(rows, start=1):
        event = row["event"]
        year = int(row["year"])
        transcript_url = row["link"]
        title = row["title"] or f"{event} session"

        host.log(f"[source={source_id}] [{idx}/{len(rows)}] Fetching transcript JSON: {transcript_url}")

        try:
            resp = requests.get(transcript_url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            host.log(f"ERROR: [source={source_id}] Failed to fetch/parse JSON for {transcript_url}: {e}")
            continue

        segments = flatten_wwdc_transcript_json(data)
        if not segments:
            host.log(f"[source={source_id}] Skipping empty transcript for {transcript_url}")
            continue

        session_year_from_url, session_id = extract_wwdc_session_id_from_url(transcript_url)
        effective_year = year or session_year_from_url

        md = wwdc_segments_to_markdown(
            url=transcript_url,
            event=event,
            year=effective_year,
            session_id=session_id,
            title=title,
            segments=segments,
        )
        _, md = apply_markdown_cleanup_pipeline(md)

        page_filename = page_filename_for_url(transcript_url)
        page_path = os.path.join(pages_dir, page_filename)
        new_hash = _sha256(md)

        entry = pages_meta.get(page_filename, {})
        old_hash = entry.get("hash")

        if old_hash == new_hash:
            host.log(f"[source={source_id}] Unchanged WWDC transcript: {page_filename}")
            continue

        changed_count += 1
        if dry_run:
            host.log(f"[source={source_id}] Would update WWDC transcript: {page_filename} [dry-run]")
            continue

        try:
            with open(page_path, "w", encoding="utf-8") as f:
                f.write(md)
        except Exception as e:
            host.log(f"ERROR: [source={source_id}] Failed to write markdown for WWDC transcript {transcript_url}: {e}")
            continue

        pages_meta[page_filename] = {
            "url": transcript_url,
            "hash": new_hash,
            "last_updated": _now_iso(),
        }

        host.log(f"[source={source_id}] Updated WWDC transcript markdown: {page_filename}")

    if not dry_run:
        meta["pages"] = pages_meta
        meta["last_crawled"] = _now_iso()
        _save_meta(host, source_id, meta)

    host.log(
        f"[source={source_id}] WWDC transcript crawl complete. Changed pages: {changed_count}"
        + (" [dry-run]" if dry_run else "")
    )


def crawl_source(host: CrawlHost, source: dict[str, Any], dry_run: bool = False) -> None:
    _ensure_project_on_path(host.project_root)
    source_id = source["id"]
    extra = source.get("extra") or {}
    if extra.get("type") == "wwdc_transcripts":
        crawl_wwdc_transcripts_source(host, source, dry_run=dry_run)
        return

    if source.get("crawler") != "playwright":
        host.log("[source={}] Only Playwright crawler is supported; skipping.".format(source_id))
        return
    if not _HAS_PLAYWRIGHT:
        host.log(
            "[source={}] Playwright is required. Run: pip install playwright html2text && playwright install chromium".format(
                source_id
            )
        )
        return

    from webui_backend.apple_docs_extract import build_apple_doc_page, render_apple_doc_to_markdown
    from webui_backend.apple_docs_fetcher import fetch_apple_doc_raw

    start_url = source["url"]
    max_depth = int(source.get("max_depth", 3))
    start_parsed = urlparse(start_url)
    start_path = (start_parsed.path or "").strip("/")
    start_segments = [s for s in start_path.split("/") if s]
    if start_segments:
        allowed_prefix = "/" + "/".join(start_segments[:2]) + "/"
    else:
        allowed_prefix = "/"

    doc_only = source.get("doc_only", "/documentation/" in (start_parsed.path or ""))
    effective_path_prefixes = source.get("path_prefixes") or host.runtime.framework_root_prefixes
    effective_excluded = source.get("excluded_path_substrings") or host.runtime.excluded_path_substrings

    host.log(
        f"[source={source_id}] Start deep crawl: {start_url} (max_depth={max_depth}) [Playwright]"
        + (" [doc_only]" if doc_only else "")
        + (" [dry-run]" if dry_run else "")
    )

    meta = _load_meta(host, source_id, start_url)
    pages_meta: dict[str, Any] = meta.get("pages", {})
    _, pages_dir = _source_dirs(host, source_id)
    if not dry_run:
        _ensure_dir(pages_dir)

    seed_urls = meta.get("seed_urls") or source.get("seed_urls") or []

    changed_count = 0
    url_status: dict[str, str] = {}
    ordered_urls: list[str] = []
    processed_urls: set[str] = set()
    prefix_norm = (allowed_prefix or "/").rstrip("/")

    def process_single_page(result: CrawlResult, is_callback: bool = False) -> bool:
        nonlocal changed_count, pages_meta

        url = result.url
        parsed = urlparse(url)
        same_host = parsed.netloc == start_parsed.netloc
        path = (parsed.path or "").rstrip("/")

        if not same_host or not (path == prefix_norm or path.startswith(prefix_norm + "/")):
            if not is_callback:
                url_status[url] = "non_doc"
            return False
        if doc_only and "/documentation" not in (parsed.path or ""):
            if not is_callback:
                url_status[url] = "non_doc"
            return False
        if any(sub in path.lower() for sub in effective_excluded):
            if not is_callback:
                url_status[url] = "non_doc"
            return False
        if source_id == "swift_book":
            slug = path.split("/")[-1] if path else ""
            if slug in SWIFT_BOOK_EXCLUDED_SLUGS:
                if not is_callback:
                    url_status[url] = "non_doc"
                return False
            if (
                SWIFT_BOOK_ALLOWED_SLUGS
                and slug not in SWIFT_BOOK_ALLOWED_SLUGS
                and slug != "the-swift-programming-language"
            ):
                if not is_callback:
                    url_status[url] = "non_doc"
                return False
        allowed = False
        for root in effective_path_prefixes:
            r = (root or "").rstrip("/")
            if not r:
                continue
            if path == r or path.startswith(r + "/"):
                allowed = True
                break
        if not allowed:
            if not is_callback:
                url_status[url] = "non_doc"
            return False
        if not result.success:
            if not is_callback:
                url_status[url] = "failed"
            return False

        html = getattr(result, "cleaned_html", None) or getattr(result, "html", "") or ""
        if not html:
            if not is_callback:
                url_status[url] = "empty"
            return False

        if _HAS_PLAYWRIGHT and doc_only and "developer.apple.com/documentation" in url:
            try:
                raw = fetch_apple_doc_raw_safe(fetch_apple_doc_raw, url)
                page = build_apple_doc_page(raw)
                md = render_apple_doc_to_markdown(page)
            except Exception as e:
                if not is_callback:
                    host.log(f"WARNING: [source={source_id}] Apple pipeline failed for {url}: {e}; skipping (no fallback)")
                return False
        else:
            md = html_to_markdown(html)

        _, md = apply_markdown_cleanup_pipeline(md)

        md_stripped = md.strip() if md else ""
        if md_stripped and md_stripped.startswith("```") and md_stripped.endswith("```"):
            fence_count = md_stripped.count("```")
            if fence_count == 2:
                if not is_callback:
                    host.log(
                        f"WARNING: [source={source_id}] Markdown wrapped in single code block for {url}; "
                        "this indicates fallback conversion issue"
                    )

        if not md:
            if not is_callback:
                url_status[url] = "normalized_empty"
            return False

        page_filename = page_filename_for_url(url)
        page_path = os.path.join(pages_dir, page_filename)
        new_hash = _sha256(md)

        entry = pages_meta.get(page_filename, {})
        old_hash = entry.get("hash")

        if old_hash == new_hash:
            if not is_callback:
                if not host.is_cli:
                    host.log(f"[source={source_id}] Unchanged: {url}")
                url_status[url] = "unchanged"
            return True

        nonlocal changed_count
        changed_count += 1
        if dry_run:
            if not is_callback:
                if not host.is_cli:
                    host.log(f"[source={source_id}] Would update: {page_filename} [dry-run]")
                url_status[url] = "would_update"
            return True

        try:
            with open(page_path, "w", encoding="utf-8") as f:
                f.write(md)
        except Exception as e:
            if not is_callback:
                host.log(f"ERROR: [source={source_id}] Failed to write markdown for {url}: {e}")
            return False

        pages_meta[page_filename] = {
            "url": url,
            "hash": new_hash,
            "last_updated": _now_iso(),
        }
        try:
            from domain.services.markdown_meta import parse_and_strip_meta_block

            page_meta, _ = parse_and_strip_meta_block(md)
            for key in ("framework", "doc_kind", "doc_scope"):
                val = (page_meta or {}).get(key)
                if val:
                    pages_meta[page_filename][key] = val
        except Exception:
            pass

        if not is_callback:
            if not host.is_cli:
                host.log(f"[source={source_id}] Updated markdown: {page_filename}")
            url_status[url] = "updated"
        else:
            if changed_count % 10 == 0:
                meta["pages"] = pages_meta
                _save_meta(host, source_id, meta)

        return True

    def on_page_callback(result: CrawlResult) -> None:
        url = result.url
        if url not in processed_urls:
            processed_urls.add(url)
            process_single_page(result, is_callback=True)

    try:
        results = asyncio.run(
            run_async_crawl_playwright(
                start_url,
                max_depth,
                allowed_prefix,
                doc_only,
                host.runtime,
                host.log,
                extra_seed_urls=seed_urls,
                on_page_processed=on_page_callback if not dry_run else None,
                allowed_path_prefixes=effective_path_prefixes,
                excluded_path_substrings=effective_excluded,
            )
        )
    except Exception as e:
        host.log(f"ERROR: Crawler exception for source '{source_id}': {e}")
        return

    total = len(results)
    for r in results:
        u = getattr(r, "url", None) or "(unknown)"
        if u not in ordered_urls:
            ordered_urls.append(u)
        if u not in url_status:
            url_status[u] = "failed" if not getattr(r, "success", False) else "queued"

    for i, result in enumerate(results, start=1):
        url = result.url
        if host.is_cli:
            host.log(f"  Processing [{i}/{total}]: {url}")

        if url in processed_urls:
            cli_progress(host, f"Crawl {source_id}", i, total)
            continue

        process_single_page(result, is_callback=False)
        cli_progress(host, f"Crawl {source_id}", i, total)

    if not dry_run:
        meta["pages"] = pages_meta
        meta["last_crawled"] = _now_iso()
        _save_meta(host, source_id, meta)

    host.log(
        f"[source={source_id}] Crawl finished. {total} pages, "
        f"{changed_count} updated/would-update markdown files."
    )

    if host.is_cli and ordered_urls:
        print(f"\n[source={source_id}] URL statuses:")
        for u in ordered_urls:
            st = url_status.get(u, "unknown")
            print(f"  [{st:15}] {u}")


def cli_progress(host: CrawlHost, prefix: str, current: int, total: int) -> None:
    if not host.is_cli or total <= 0:
        return
    percent = int(current * 100 / total)
    msg = f"{prefix}: {current}/{total} ({percent}%)"
    print("\r" + msg.ljust(80), end="", flush=True)
    if current >= total:
        print()


def run_crawl_all_sources(
    host: CrawlHost,
    source_filter: list[str] | None = None,
    dry_run: bool = False,
    sources_override: list[dict[str, Any]] | None = None,
) -> None:
    sources = sources_override if sources_override is not None else load_sources(host.project_root)
    sources = [s for s in sources if source_filter is None or s["id"] in source_filter]
    if not sources:
        host.log("No sources to crawl (empty filter?).")
        return
    host.log(
        "Starting crawl for "
        + (f"sources {[s['id'] for s in sources]}" if source_filter else "all configured sources")
        + (" [dry-run]" if dry_run else "")
    )
    for source in sources:
        crawl_source(host, source, dry_run=dry_run)
    host.log("All sources crawled.")


def build_crawl_host(
    *,
    project_root: Path | None = None,
    webui_dir: Path | None = None,
    log: Callable[[str], None] | None = None,
    is_cli: bool = False,
) -> CrawlHost:
    pr = project_root or default_project_root()
    wd = webui_dir or resolve_webui_dir(pr)
    runtime = load_crawler_runtime_config(pr)

    def _log(msg: str) -> None:
        (log or print)(msg)

    return CrawlHost(project_root=pr, webui_dir=wd, log=_log, is_cli=is_cli, runtime=runtime)
