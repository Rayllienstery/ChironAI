from flask import Flask, request, Response
import os
import re
import threading
import asyncio
import time
import json
import hashlib
from datetime import datetime, timezone
import requests
from urllib.parse import urlparse

try:
    from lxml import html as lxml_html
    _HAS_LXML = True
except ImportError:
    _HAS_LXML = False

try:
    import html2text
    _HAS_HTML2TEXT = True
except ImportError:
    html2text = None
    _HAS_HTML2TEXT = False

try:
    from playwright.async_api import async_playwright
    _HAS_PLAYWRIGHT = True
except ImportError:
    async_playwright = None
    _HAS_PLAYWRIGHT = False

from crawl4ai import AsyncWebCrawler, CrawlerRunConfig
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter
from crawl4ai.content_scraping_strategy import LXMLWebScrapingStrategy

from apple_docs_fetcher import fetch_apple_doc_raw
from apple_docs_extract import build_apple_doc_page, render_apple_doc_to_markdown

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    VectorParams,
    Distance,
    PointStruct,
    PointIdsList,
    PayloadSchemaType,
)
from qdrant_client.http.exceptions import ResponseHandlingException

from langchain_text_splitters import HTMLSemanticPreservingSplitter


app = Flask(__name__)

# Global variables (for legacy /crawl UI and logging)
log_queue = []
stop_flag = False
id_counter = 1

IS_CLI = False  # Set to True in CLI mode so we can adapt logging/progress

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAG_SOURCES_DIR = os.path.join(BASE_DIR, "rag_sources")
COLLECTION_FILE = os.path.join(BASE_DIR, "last_collection.txt")

# Single logical collection for all dev docs (RAG)
RAG_COLLECTION_NAME = "dev_docs"

# Single source: Apple Developer documentation only, depth 4.
# Uses Playwright for JS-rendered pages and RAG-optimized pipeline (apple_docs_fetcher + apple_docs_extract).
# seed_urls: extra entry points so the crawler discovers pages even when the index page is SPA with few DOM links.
SOURCES = [
    {
        "id": "apple_documentation",
        "url": "https://developer.apple.com/documentation",
        "max_depth": 4,
        "crawler": "playwright",
        "doc_only": True,
        "seed_urls": [
            "https://developer.apple.com/documentation/swift",
            "https://developer.apple.com/documentation/swiftui",
            "https://developer.apple.com/documentation/uikit",
            "https://developer.apple.com/documentation/foundation",
            "https://developer.apple.com/documentation/combine",
            "https://developer.apple.com/documentation/widgetkit",
        ],
    },
]

# Файлы/страницы с этими подстроками в имени не индексируются (шумные справочники, промо/шоукейс).
# Имя файла = slug из URL (например system-fonts-5ee35c84.md). Добавляй сюда подстроки, которые отсекают низкоценные страницы.
INDEX_EXCLUDE_FILENAME_SUBSTRINGS = [
    # Справочные дампы (гигантские списки, таблицы)
    "system-fonts",
    "sf-symbols",
    "symbols-",
    "character-set",
    "unicode-",
    "key-codes",
    "keycodes",
    "glyph-",
    # Промо / шоукейс / featured (игры, App of the Day — не техдока)
    "adventure",         # hello-kitty-island-adventure и подобные промо игр
    "spotlight",        # Apple Spotlight stories
    "featured",         # featured apps/games
    "app-of-the-day",
    # Новости / анонсы / маркетинг для девелоперов (не техдока)
    "news-",            # developer.apple.com/news/...
    "newsroom",         # developer.apple.com/newsroom/...
    "apple-news",       # страницы про Apple News / News Partner Program
    # Навигационные страницы-оглавления (порталы ресурсов, без собственной техдоки)
    "resources-",       # developer.apple.com/.../resources
    # Глобальный маркетинг / карты / дев-центры / инвесторские страницы (не dev‑дока)
    "index-bbd8a4aa",
    "index-e86693b7",
    "index-92997f4f",
    "index-736d3707",
    "index-5103b240",
    "index-70f9f2b3",
    "index-f8089eb8",
    "index-8ac5cb19",
    "index-441438f1",
    "index-587515ca",
    "index-4cfc0399",
    "index-7e38bb46",
    "index-07e78366",
    "index-76b9f20c",
    "index-82c29db0",
    "index-87db839d",
    # Магазин / TV & Home / логин / активности (вне dev‑доки)
    "bag-75cad20f",
    "tv-home-4b7b3889",
    "login-eb7de4d3",
    "accelerator-e234e5a9",
    # Пресс‑релиз про родительский контроль — policy/маркетинг, не API‑дока
    "apple-expands-tools-to-help-parents-protect-kids-and-teens-online",
]

# Если в начале markdown (первые N символов) есть одна из этих подстрок — страницу не индексируем (промо/шоукейс).
INDEX_EXCLUDE_CONTENT_HEAD_CHARS = 2000  # сколько символов с начала файла проверять
INDEX_EXCLUDE_CONTENT_SUBSTRINGS = [
    "DEVELOPER STORIES",
    "APP OF THE DAY",
    "FEATURED APP",
]


def log(message: str) -> None:
    """Append message to in-memory log queue and print to stdout."""
    print(message)
    # В CLI-режиме SSE-лог не используется, можно не раздувать очередь
    if not IS_CLI:
        log_queue.append(message)


def cli_progress(prefix: str, current: int, total: int) -> None:
    """
    Simple one-line CLI progress indicator (overwrites same line).
    Does nothing when not in CLI mode.
    """
    if not IS_CLI or total <= 0:
        return
    percent = int(current * 100 / total)
    msg = f"{prefix}: {current}/{total} ({percent}%)"
    # pad to avoid leftover chars from previous longer line
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

EMBED_BATCH_SIZE = 6  # embeddinggemma тяжёлый; меньший батч — быстрее ответ, меньше таймаутов
EMBED_REQUEST_TIMEOUT = 300  # секунд на один запрос к /api/embed (embeddinggemma может долго думать)

# Имя embed‑модели в Ollama. Должно совпадать с rag_client.EMBED_MODEL_NAME.
# По умолчанию используем bge-m3; можно переопределить через переменную окружения
# RAG_EMBED_MODEL (но провайдером остаётся Ollama).
EMBED_MODEL_NAME = os.getenv("RAG_EMBED_MODEL", "mxbai-embed-large")

# Базовый endpoint Ollama для эмбеддингов. Если нужно использовать другой Ollama-хост/порт,
# меняем только эту переменную (или OLLAMA_EMBED_URL в rag_client.py).
OLLAMA_EMBED_URL = os.getenv("OLLAMA_EMBED_URL", "http://localhost:11434/api/embed")


EMBED_RETRY_ATTEMPTS = 2
# более щадящий backoff, чтобы дать Ollama «отдышаться»
EMBED_RETRY_SLEEP = (1, 3)  # seconds between attempts
EMBED_TRUNCATE_CHARS = 4096  # максимум символов на один текст при деградации


def get_embeddings(texts, model_name: str = EMBED_MODEL_NAME):
    """
    Embed a list of texts via Ollama.

    Единственная точка, которую нужно менять при смене embed‑модели:
    - EMBED_MODEL_NAME / OLLAMA_EMBED_URL (или RAG_EMBED_MODEL / OLLAMA_EMBED_URL в окружении);
    - при необходимости — формат разбора ответа.

    Ожидаемый формат ответа Ollama /api/embed:
    {
      "embeddings": [
        [float, float, ...],  # один вектор на каждый входной текст
        ...
      ]
    }
    """
    if not texts:
        return []

    def _call_embed(batch: list[str]) -> list[list[float]]:
        """
        Низкоуровневый вызов /api/embed для конкретного батча.
        Предполагает, что размер batch разумный (без рекурсивного деления).
        """
        response = requests.post(
            OLLAMA_EMBED_URL,
            json={"model": model_name, "input": batch},
            timeout=EMBED_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings")
        if embeddings is None:
            raise ValueError("No 'embeddings' key in Ollama response")
        if len(embeddings) != len(batch):
            raise ValueError(
                f"Ollama /api/embed returned {len(embeddings)} embeddings for batch size {len(batch)}"
            )
        return embeddings

    def _embed_with_backoff(batch: list[str]) -> list[list[float]]:
        """
        Попытка заэмбеддить batch с ретраями. Если весь batch стабильно падает,
        пробуем рекурсивно разбить его на части; при размере 1 деградируем
        до укороченного текста.
        """
        last_error: Exception | None = None
        for attempt in range(EMBED_RETRY_ATTEMPTS):
            try:
                return _call_embed(batch)
            except Exception as e:
                last_error = e
                if attempt < EMBED_RETRY_ATTEMPTS - 1:
                    sleep_sec = EMBED_RETRY_SLEEP[attempt]
                    log(
                        f"⚠️ Embedding attempt {attempt + 1} failed for batch(size={len(batch)}): {e}; "
                        f"retry in {sleep_sec}s"
                    )
                    time.sleep(sleep_sec)

        # Если все попытки для всего батча не удались — пробуем смягчить нагрузку.
        if len(batch) <= 1:
            # Один проблемный текст: попробуем укоротить его.
            text = batch[0]
            short = text[:EMBED_TRUNCATE_CHARS]
            if short != text:
                try:
                    log(
                        f"⚠️ Embedding failed for full text (len={len(text)}); "
                        f"trying truncated version (len={len(short)})"
                    )
                    return _call_embed([short])
                except Exception as e2:
                    raise RuntimeError(
                        f"Embedding failed for single text even after truncation: {e2}"
                    ) from last_error
            raise RuntimeError(
                f"Embedding failed for single text (len={len(text)}): {last_error}"
            ) from last_error

        # Делим batch пополам и пробуем эмбеддить части отдельно.
        mid = len(batch) // 2
        left = _embed_with_backoff(batch[:mid])
        right = _embed_with_backoff(batch[mid:])
        return left + right

    all_embeddings: list[list[float]] = []
    total_batches = (len(texts) + EMBED_BATCH_SIZE - 1) // EMBED_BATCH_SIZE
    for batch_idx, i in enumerate(range(0, len(texts), EMBED_BATCH_SIZE), start=1):
        if IS_CLI and total_batches > 1:
            ts = datetime.now().strftime("%H:%M:%S")
            log(f"  [{ts}] embed batch {batch_idx}/{total_batches} ({len(texts)} chunks)")
        batch = texts[i : i + EMBED_BATCH_SIZE]
        try:
            emb = _embed_with_backoff(batch)
            all_embeddings.extend(emb)
        except Exception as e:
            log(
                f"❌ Embedding error for batch {batch_idx}/{total_batches} "
                f"(size={len(batch)}): {e}"
            )
            return []

    return all_embeddings


def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _point_id_from_hash(h: str) -> int:
    """
    Build a Qdrant-compatible unsigned integer point id from a sha256 hex string.
    Uses the first 16 hex chars (64 bits), which is deterministic and fits u64.
    """
    h = (h or "0" * 16)[:16]
    return int(h, 16)


def _source_dirs(source_id: str) -> tuple[str, str]:
    """Return (source_root, pages_dir) for a given source id."""
    root = os.path.join(RAG_SOURCES_DIR, source_id)
    pages = os.path.join(root, "pages")
    return root, pages


def _meta_path(source_id: str) -> str:
    root, _ = _source_dirs(source_id)
    return os.path.join(root, "meta.json")


def _load_meta(source_id: str, source_url: str) -> dict:
    """Load per-source meta.json, returning a default structure if missing."""
    path = _meta_path(source_id)
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            # Minimal validation / backfill
            data.setdefault("source_id", source_id)
            data.setdefault("source_url", source_url)
            data.setdefault("hash_algo", "sha256")
            data.setdefault("pages", {})
            return data
        except Exception as e:
            log(f"⚠️ Failed to read meta.json for {source_id}: {e}")
    return {
        "source_id": source_id,
        "source_url": source_url,
        "last_crawled": None,
        "hash_algo": "sha256",
        "pages": {},
    }


def _save_meta(source_id: str, meta: dict) -> None:
    """Persist per-source meta.json."""
    root, _ = _source_dirs(source_id)
    _ensure_dir(root)
    path = _meta_path(source_id)
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
    except Exception as e:
        log(f"❗ Failed to write meta.json for {source_id}: {e}")


def _slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    return text or "page"


def _page_filename_for_url(url: str) -> str:
    """
    Build a stable markdown filename for a URL.
    Combination of last path segment (or 'index') and short hash of URL.
    """
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


def _html_to_markdown_regex(html: str) -> str:
    """Fallback regex-based HTML→markdown when lxml is not available."""
    if not html:
        return ""
    html = re.sub(
        r"<(nav|header|footer|aside)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL
    )
    html = re.sub(
        r"<div[^>]+(nav|navigation|breadcrumb|breadcrumbs|sidebar|toc)[^>]*>.*?</div>",
        "", html, flags=re.IGNORECASE | re.DOTALL
    )
    html = re.sub(
        r"<ul[^>]+(nav|navigation|breadcrumb|breadcrumbs)[^>]*>.*?</ul>",
        "", html, flags=re.IGNORECASE | re.DOTALL
    )
    html = re.sub(
        r"<([a-zA-Z0-9]+)[^>]+role=\"navigation\"[^>]*>.*?</\1>",
        "", html, flags=re.IGNORECASE | re.DOTALL
    )
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", html, flags=re.IGNORECASE | re.DOTALL)

    def _replace_heading(match):
        level, text = match.group(1), match.group(2).strip()
        return f"\n\n{'#' * int(level)} {text}\n\n"
    html = re.sub(r"<h([1-3])[^>]*>(.*?)</h\1>", _replace_heading, html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<p[^>]*>(.*?)</p>", r"\1\n\n", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<li[^>]*>(.*?)</li>", r"- \1\n", html, flags=re.IGNORECASE | re.DOTALL)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    lines = [ln.rstrip() for ln in text.splitlines()]
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines).strip())
    return text


def _html_to_markdown_dom(html: str) -> str:
    """
    DOM-based deterministic HTML → markdown.
    - Drops nav/header/footer/aside/script/style and role=navigation.
    - Preserves h1–h6, p, pre/code blocks, inline code, tables.
    """
    if not html:
        return ""
    try:
        root = lxml_html.fromstring(html)
    except Exception:
        return _html_to_markdown_regex(html)

    # Remove chrome and noise (collect first to avoid mutating while iterating)
    to_remove: list = []
    for tag in ("script", "style", "nav", "header", "footer", "aside"):
        to_remove.extend(root.iter(tag))
    to_remove.extend(root.xpath("//*[@role='navigation']"))
    for el in to_remove:
        parent = el.getparent()
        if parent is not None:
            parent.remove(el)

    # Top-level content blocks in document order. Include divs that look like code blocks
    # (Apple and other doc sites often use div.code, div.snippet, etc.).
    blocks = root.xpath(
        "//*[self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6 "
        "or self::p or self::pre or self::table or self::ul or self::ol or self::li "
        "or (self::div and (contains(concat(' ', normalize-space(@class), ' '), ' code ') "
        "or contains(concat(' ', normalize-space(@class), ' '), ' snippet ') "
        "or contains(concat(' ', normalize-space(@class), ' '), ' sample ') "
        "or .//pre or .//code))]"
    )
    ancestor_block_tags = {"h1", "h2", "h3", "h4", "h5", "h6", "p", "pre", "table", "li", "div"}

    top_level = []
    for b in blocks:
        parent = b.getparent()
        is_top = True
        # если среди предков есть другой «контентный» блок, не считаем этот элемент верхнеуровневым
        while parent is not None:
            tag = (parent.tag or "").lower()
            if tag in ancestor_block_tags:
                is_top = False
                break
            parent = parent.getparent()
        if is_top:
            top_level.append(b)

    out: list[str] = []
    for el in top_level:
        tag = (el.tag or "").lower()
        if tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            text = (el.text_content() or "").strip()
            if text:
                out.append("\n\n" + "#" * level + " " + text + "\n\n")
        elif tag == "p":
            text = (el.text_content() or "").strip()
            if text:
                out.append(text + "\n\n")
        elif tag == "pre":
            code_el = el.find(".//code")
            raw = (code_el.text_content() if code_el is not None else el.text_content()) or ""
            raw = raw.strip()
            if raw:
                out.append("\n\n```\n" + raw + "\n```\n\n")
        elif tag == "div":
            raw = (el.text_content() or "").strip()
            if raw and len(raw) > 2:
                out.append("\n\n```\n" + raw + "\n```\n\n")
        elif tag == "table":
            rows = el.findall(".//tr")
            if not rows:
                continue
            cells = []
            for tr in rows:
                row_cells = tr.findall("td") or tr.findall("th")
                cells.append([(c.text_content() or "").strip().replace("|", "\\|") for c in row_cells])
            if not cells:
                continue
            sep = "| " + " | ".join(["---"] * len(cells[0])) + " |"
            out.append("\n\n" + "| " + " | ".join(cells[0]) + " |\n" + sep + "\n")
            for row in cells[1:]:
                out.append("| " + " | ".join(row) + " |\n")
            out.append("\n")
        elif tag == "li":
            text = (el.text_content() or "").strip()
            if text:
                out.append("- " + text + "\n")
        elif tag in ("ul", "ol"):
            # Content already emitted via li
            continue

    text = "".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


# Строки, которые выкидываем из markdown перед индексацией (UI-болванка, не контент).
MARKDOWN_BOILERPLATE_LINES = [
    "View in English",
    "View in Russian",
    "В English",
    "На русском",
    "Table of Contents",
    "Contents",
]


def _strip_markdown_boilerplate(md: str) -> str:
    """Удаляет строки, которые совпадают с известной UI-болванкой (View in English и т.п.)."""
    if not md:
        return ""
    boilerplate_lower = {s.strip().lower() for s in MARKDOWN_BOILERPLATE_LINES}
    lines = md.split("\n")
    out = []
    for ln in lines:
        stripped = ln.strip()
        if stripped.lower() in boilerplate_lower:
            continue
        # Строка-ссылка вида [View in English](url)
        if stripped.startswith("[") and "view in english" in stripped.lower():
            continue
        if stripped.startswith("[") and "view in russian" in stripped.lower():
            continue
        out.append(ln)
    text = "\n".join(out)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def _normalize_markdown_whitespace(md: str) -> str:
    """
    Safe whitespace normalization for markdown:
    - Strip trailing whitespace from each line.
    - Strip leading/trailing blank lines.
    - Collapse 2+ spaces to 1 in non-code lines (not inside fenced ``` blocks, not indented with 4+ spaces).
    Does not strip leading spaces from lines (would break indented code blocks).
    """
    if not md:
        return ""
    lines = md.split("\n")
    lines = [ln.rstrip() for ln in lines]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    in_fenced = False
    result = []
    for ln in lines:
        if ln.strip().startswith("```"):
            in_fenced = not in_fenced
            result.append(ln)
            continue
        if in_fenced:
            result.append(ln)
            continue
        # Indented code (4+ spaces at start): leave as-is
        if len(ln) - len(ln.lstrip()) >= 4 and ln.strip():
            result.append(ln)
            continue
        # Normal line: collapse 2+ spaces to 1
        result.append(re.sub(r" {2,}", " ", ln))
    return "\n".join(result)


def _html_to_markdown_html2text(html: str) -> str:
    """
    HTML → markdown via html2text. Preserves code blocks (pre/code), lists, headings.
    Use for documentation pages where code samples must be retained.
    """
    if not _HAS_HTML2TEXT or not html:
        return ""
    h = html2text.HTML2Text()
    h.ignore_links = False
    h.ignore_images = True
    h.body_width = 0
    h.ignore_emphasis = False
    h.single_line_break = False
    try:
        raw = h.handle(html)
    except Exception:
        return ""
    return _normalize_markdown_whitespace(_strip_markdown_boilerplate(raw))


def html_to_markdown(html: str, prefer_code_preservation: bool = True) -> str:
    """
    Deterministic HTML → markdown. When html2text is available and prefer_code_preservation
    is True, uses it to preserve code blocks (pre/code) and structure. Otherwise uses
    DOM-based normalizer (lxml) or regex fallback. Boilerplate (View in English etc.) removed at end.
    """
    if not html:
        return ""
    if prefer_code_preservation and _HAS_HTML2TEXT:
        md = _html_to_markdown_html2text(html)
        if md and len(md.strip()) > 100:
            return md
    if _HAS_LXML:
        raw = _html_to_markdown_dom(html)
        return _normalize_markdown_whitespace(_strip_markdown_boilerplate(raw))
    raw = _html_to_markdown_regex(html)
    return _normalize_markdown_whitespace(_strip_markdown_boilerplate(raw))


class _CrawlResult:
    """Minimal result object compatible with Crawl4AI-style results (url, success, html)."""

    __slots__ = ("url", "success", "html")

    def __init__(self, url: str, success: bool, html: str = ""):
        self.url = url
        self.success = success
        self.html = html


async def run_async_crawl_playwright(
    start_url: str,
    max_depth: int,
    allowed_prefix: str,
    doc_only: bool,
    extra_seed_urls: list[str] | None = None,
) -> list:
    """
    BFS crawl using Playwright. Fetches full page HTML (after JS); good for
    documentation sites where code blocks may be in custom elements. Returns
    list of _CrawlResult(url, success, html). Requires: pip install playwright && playwright install chromium.
    """
    if not _HAS_PLAYWRIGHT:
        log("⚠️ Playwright not installed; run: pip install playwright && playwright install chromium")
        return []
    start_parsed = urlparse(start_url)
    base_url = f"{start_parsed.scheme or 'https'}://{start_parsed.netloc}"
    visited: set[str] = set()
    results: list[_CrawlResult] = []
    queue: list[tuple[str, int]] = [(start_url, 0)]
    for u in extra_seed_urls or []:
        u = (u or "").strip()
        if u and u != start_url:
            queue.append((u, 0))
    prefix_p = allowed_prefix.rstrip("/")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            while queue:
                url, depth = queue.pop(0)
                if url in visited or depth > max_depth:
                    continue
                visited.add(url)
                parsed = urlparse(url)
                if parsed.netloc != start_parsed.netloc:
                    continue
                path_p = (parsed.path or "").rstrip("/")
                if not (path_p == prefix_p or path_p.startswith(prefix_p + "/")):
                    continue
                if doc_only and "/documentation" not in (parsed.path or ""):
                    continue
                log(f"  Fetching [depth {depth}]: {url}")
                try:
                    page = await browser.new_page()
                    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                    await page.wait_for_load_state("networkidle", timeout=10000)
                except Exception:
                    await page.close()
                    results.append(_CrawlResult(url, False, ""))
                    continue
                try:
                    body = await page.evaluate("""() => {
                        const main = document.querySelector('main') || document.querySelector('article') || document.body;
                        return main ? main.innerHTML : document.body.innerHTML;
                    }""")
                except Exception:
                    body = ""
                await page.close()
                if not body:
                    results.append(_CrawlResult(url, False, ""))
                    continue
                full_html = f"<!DOCTYPE html><html><head></head><body>{body}</body></html>"
                results.append(_CrawlResult(url, True, full_html))
                if depth >= max_depth:
                    continue
                try:
                    page2 = await browser.new_page()
                    await page2.goto(url, wait_until="domcontentloaded", timeout=20000)
                    await page2.wait_for_load_state("networkidle", timeout=15000)
                    links = await page2.evaluate("""() => {
                        const out = [];
                        document.querySelectorAll('a[href]').forEach(a => {
                            const h = a.getAttribute('href');
                            if (h && (h.startsWith('http') || h.startsWith('/'))) out.push(h);
                        });
                        return out;
                    }""")
                    await page2.close()
                except Exception:
                    links = []
                for raw in links:
                    href = raw.split("#")[0].strip()
                    if not href:
                        continue
                    if href.startswith("//"):
                        next_url = f"{start_parsed.scheme}:{href}"
                    elif href.startswith("/"):
                        next_url = f"{base_url.rstrip('/')}{href}"
                    elif href.startswith("http"):
                        next_url = href
                    else:
                        continue
                    try:
                        next_parsed = urlparse(next_url)
                        if next_parsed.netloc != start_parsed.netloc:
                            continue
                        next_path = (next_parsed.path or "").rstrip("/")
                        if not (next_path == prefix_p or next_path.startswith(prefix_p + "/")):
                            continue
                        if doc_only and "/documentation" not in (next_parsed.path or ""):
                            continue
                        if next_url not in visited:
                            queue.append((next_url, depth + 1))
                    except Exception:
                        pass
        finally:
            await browser.close()
    return results


async def run_async_crawl(start_url, max_depth: int = 3):
    # Only follow http/https links (skip ms-appinstaller:, mailto:, etc.)
    url_filter = URLPatternFilter(patterns=["http*"])
    strategy = BFSDeepCrawlStrategy(
        max_depth=max_depth,
        include_external=False,
        filter_chain=FilterChain([url_filter]),
    )
    config = CrawlerRunConfig(
        deep_crawl_strategy=strategy,
        scraping_strategy=LXMLWebScrapingStrategy(),
        verbose=False
    )
    log(f"🔍 [1/4] Start deep crawl: {start_url}")
    async with AsyncWebCrawler() as crawler:
        results = await crawler.arun(start_url, config=config)
    return results


def collection_name_from_url(_: str) -> str:
    """
    Single logical Qdrant collection for all sources.
    URL is ignored intentionally.
    """
    return RAG_COLLECTION_NAME


def _write_collection_file(name: str) -> None:
    """Persist last used collection name for rag_client/search_rag."""
    try:
        with open(COLLECTION_FILE, "w", encoding="utf-8") as f:
            f.write(name)
    except Exception:
        # Non-fatal
        pass


# Chunk size limits (chars) for RAG
CHUNK_MAX_SIZE = 1200
CHUNK_MIN_SIZE = 300

# Qdrant upsert batch size (points). We batch vectors across files to reduce
# HTTP roundtrips while keeping memory usage predictable.
BATCH_UPSERT_SIZE = 200


def _split_markdown_into_chunks(
    md: str,
    max_chunk_size: int = CHUNK_MAX_SIZE,
    min_chunk_size: int = CHUNK_MIN_SIZE,
) -> list[tuple[str, list[str]]]:
    """
    Split markdown into chunks with section_path (heading hierarchy).
    Returns list of (chunk_text, section_path). section_path is e.g. ["Concurrency", "Actors"].
    Prefers starting new chunks at headings; enforces min/max chunk size.
    """
    if not md:
        return []
    paragraphs = [p.strip() for p in md.split("\n\n") if p.strip()]
    chunks: list[tuple[str, list[str]]] = []
    current: list[str] = []
    current_len = 0
    section_path: list[str] = []

    def _flush():
        nonlocal current, current_len
        if not current:
            return
        text = "\n\n".join(current)
        chunks.append((text, list(section_path)))
        current = []
        current_len = 0

    for p in paragraphs:
        stripped = p.lstrip()
        is_heading = stripped.startswith("#")
        if is_heading:
            depth = 0
            while depth < len(stripped) and stripped[depth] == "#":
                depth += 1
            title = stripped[depth:].strip()
            if depth >= 1 and title:
                section_path = section_path[: depth - 1] + [title]

            if current and current_len >= max_chunk_size * 0.5:
                _flush()
            current.append(p)
            current_len += len(p) + 2
            continue

        if current_len + len(p) + 2 > max_chunk_size and current:
            _flush()
            current = [p]
            current_len = len(p) + 2
        else:
            current.append(p)
            current_len += len(p) + 2

    _flush()

    # Merge adjacent chunks below min_chunk_size when same section_path
    merged: list[tuple[str, list[str]]] = []
    i = 0
    while i < len(chunks):
        text, path = chunks[i]
        while (
            i + 1 < len(chunks)
            and len(text) < min_chunk_size
            and chunks[i + 1][1] == path
            and len(text) + 2 + len(chunks[i + 1][0]) <= max_chunk_size
        ):
            i += 1
            text += "\n\n" + chunks[i][0]
        merged.append((text, path))
        i += 1
    return merged


_IOS_VERSION_RE = re.compile(r"\biOS\s+(\d+(?:\.\d+)*)\+?", re.IGNORECASE)
_SWIFT_VERSION_RE = re.compile(r"\bSwift\s+(\d+(?:\.\d+)*)", re.IGNORECASE)


def _extract_versions(text: str) -> tuple[list[str], list[str]]:
    """
    Extract iOS and Swift version markers from a chunk of text.
    Returns (ios_versions, swift_versions) as sorted unique strings.
    """
    ios = {m.group(1) for m in _IOS_VERSION_RE.finditer(text or "")}
    swift = {m.group(1) for m in _SWIFT_VERSION_RE.finditer(text or "")}
    return sorted(ios), sorted(swift)


def infer_metadata(
    source_id: str,
    filename: str,
    url: str | None,
    section_path: list[str],
    text: str,
) -> dict[str, str]:
    """
    Infer high-level metadata for a chunk in a stable, extensible way.

    Stable keys (string values only):
    - language: swift / objc / rust / js / ts / shell / dockerfile / unknown
    - technology: swiftui / uikit / foundation / concurrency / distributed / nodejs / express / ... / unknown
    - domain: framework_guide / api_ref / language_guide / app_store / tooling / infra / policy / ml / graphics / networking / documentation
    - product: ios / ipados / macos / tvos / watchos / visionos / server / tooling / unknown
    - doc_type: documentation / howto / sample_code / policy / legal / marketing / help_center

    Heuristics are intentionally conservative: we only set what we can infer
    with high confidence from the current Apple dev docs structure. For future
    sources (Rust, Node, etc.) extend the blocks below without changing callers.
    """
    # Defaults: safe, documentation-centric.
    language = "unknown"
    technology = "unknown"
    domain = "documentation"
    product = "unknown"
    doc_type = "documentation"

    lower_name = (filename or "").lower()
    lower_url = (url or "").lower()

    # 1. Base hints from source_id (primary partitioning of the corpus).
    if source_id == "apple_documentation":
        language = "swift"
        domain = "framework_guide"
        product = "ios"
        if "/documentation/swift" in lower_url:
            technology = "swift"
            domain = "language_guide"
        elif "/documentation/uikit" in lower_url:
            technology = "uikit"
        elif "/documentation/swiftui" in lower_url:
            technology = "swiftui"
        elif "/documentation/combine" in lower_url:
            technology = "combine"
        elif "/documentation/swiftdata" in lower_url:
            technology = "swiftdata"
        elif "/documentation/foundation" in lower_url:
            technology = "foundation"
        elif "/documentation/widgetkit" in lower_url:
            technology = "widgetkit"
        elif "/documentation/coredata" in lower_url:
            technology = "coredata"
        elif "/documentation/quartzcore" in lower_url:
            technology = "core_animation"
        elif "/documentation/avfoundation" in lower_url:
            technology = "avfoundation"
        elif "/documentation/mapkit" in lower_url:
            technology = "mapkit"
        elif "/documentation/coregraphics" in lower_url:
            technology = "coregraphics"
        elif "/documentation/storekit" in lower_url:
            technology = "storekit"
            domain = "app_store"
        elif "/documentation/xcode" in lower_url:
            technology = "xcode"
            domain = "tooling"
            product = "tooling"
        else:
            technology = "foundation"
    elif source_id == "swift_docs":
        language = "swift"
        domain = "language_guide"
        # Swift docs cover multiple platforms; leave product unknown.
    elif source_id == "swift_whats_new":
        language = "swift"
        technology = "swift"
        domain = "language_guide"
        product = "ios"
        doc_type = "release_notes"
    elif source_id == "swiftui_whats_new":
        language = "swift"
        technology = "swiftui"
        domain = "framework_guide"
        product = "ios"
        doc_type = "release_notes"
    elif source_id == "ios_whats_new":
        language = "swift"
        technology = "uikit"
        domain = "framework_guide"
        product = "ios"
        doc_type = "release_notes"
    elif source_id in {
        "apple_uikit",
        "swiftui_docs",
        "combine_docs",
        "swiftdata_docs",
        "foundation_docs",
        "coredata_docs",
        "coreanimation_docs",
        "avfoundation_docs",
        "mapkit_docs",
        "coregraphics_docs",
        "storekit_docs",
    }:
        language = "swift"
        domain = "framework_guide"
        product = "ios"
        if source_id == "apple_uikit":
            technology = "uikit"
        elif source_id == "swiftui_docs":
            technology = "swiftui"
        elif source_id == "combine_docs":
            technology = "combine"
        elif source_id == "swiftdata_docs":
            technology = "swiftdata"
        elif source_id == "foundation_docs":
            technology = "foundation"
        elif source_id == "coredata_docs":
            technology = "coredata"
        elif source_id == "coreanimation_docs":
            technology = "core_animation"
        elif source_id == "avfoundation_docs":
            technology = "avfoundation"
        elif source_id == "mapkit_docs":
            technology = "mapkit"
        elif source_id == "coregraphics_docs":
            technology = "coregraphics"
        elif source_id == "storekit_docs":
            technology = "storekit"
            domain = "app_store"
    elif source_id == "wwdc_sessions_2024":
        language = "swift"
        technology = "wwdc_sessions"
        domain = "framework_guide"
    elif source_id == "xcode_docs":
        language = "swift"
        technology = "xcode"
        domain = "tooling"
        product = "tooling"
    elif source_id == "swift_org_docs":
        language = "swift"
        domain = "language_guide"
    # Community sites / blogs.
    elif source_id in {
        "hws_swift",
        "swiftbysundell_articles",
        "kodeco_ios",
        "objc_io_issues",
        "nshipster_articles",
    }:
        language = "swift"
        # Architecture & framework guidance by default.
        domain = "framework_guide"
        doc_type = "howto"
    # Third-party service docs.
    elif source_id in {"firebase_ios", "stripe_ios"}:
        language = "swift"
        domain = "tooling"
        product = "ios"
    # Point-Free ecosystem.
    elif source_id.startswith("pf_"):
        language = "swift"
        domain = "framework_guide"
        product = "ios"
        if source_id == "pf_tca":
            technology = "tca"
        elif source_id == "pf_dependencies":
            technology = "dependencies"
        elif source_id == "pf_navigation":
            technology = "navigation"
        elif source_id == "pf_sharing":
            technology = "sharing"
        elif source_id == "pf_snapshot_testing":
            technology = "snapshot_testing"
            domain = "tooling"
        elif source_id == "pf_identified_collections":
            technology = "identified_collections"
        elif source_id == "pf_clocks":
            technology = "clocks"
            domain = "tooling"
    # Popular iOS libraries on GitHub.
    elif source_id.startswith("gh_"):
        language = "swift"
        domain = "framework_guide"
        product = "ios"
        if source_id == "gh_alamofire":
            technology = "networking"
        elif source_id == "gh_moya":
            technology = "networking"
        elif source_id in {"gh_kingfisher", "gh_sdwebimage"}:
            technology = "image_loading"
        elif source_id == "gh_snapkit":
            technology = "layout"
        elif source_id == "gh_swiftlint":
            technology = "linting"
            domain = "tooling"
        elif source_id == "gh_realm_swift":
            technology = "persistence"
        elif source_id == "gh_rxswift":
            technology = "reactive"
        elif source_id == "gh_combineext":
            technology = "combine"
        elif source_id in {"gh_quick", "gh_nimble"}:
            technology = "testing"
            domain = "tooling"
    # Future multi-language hooks (extend as new sources appear).
    elif source_id == "rust_docs":
        language = "rust"
        domain = "language_guide"
        product = "server"
    elif source_id == "node_docs":
        language = "js"
        technology = "nodejs"
        domain = "framework_guide"
        product = "server"

    # 2. Filename / path heuristics (local archive naming, slugs).
    if "swiftui" in lower_name:
        technology = "swiftui"
        domain = "framework_guide"
        # SwiftUI is cross‑platform, but most questions are iOS-centric.
        if product == "unknown":
            product = "ios"
    if "uikit" in lower_name:
        technology = "uikit"
        domain = "framework_guide"
        if product == "unknown":
            product = "ios"
    if "combine" in lower_name:
        technology = "combine"
        domain = "framework_guide"
    if "concurrency" in lower_name or "actors" in lower_name:
        technology = "concurrency"
        domain = "language_guide"
    if "distributed" in lower_name:
        technology = "distributed"
        # Distributed Swift docs live between language + infra.
        if domain == "documentation":
            domain = "language_guide"
    if "foundation" in lower_name and technology == "unknown":
        technology = "foundation"
        domain = "framework_guide"

    # App Store / commerce / distribution.
    if any(k in lower_name for k in ("storekit", "in-app-purchase", "in_app_purchase")):
        technology = "storekit"
        domain = "app_store"
        product = "ios"
    if "testflight" in lower_name:
        domain = "app_store"
        product = "ios"
    if "app-store" in lower_name or "appstore" in lower_name:
        domain = "app_store"
        if product == "unknown":
            product = "ios"

    # Tooling.
    if "xcode" in lower_name and technology == "unknown":
        technology = "xcode"
        domain = "tooling"
        product = "tooling"
    if "playgrounds" in lower_name:
        technology = "swift_playgrounds"
        domain = "tooling"
        product = "tooling"

    # Document type by filename hints.
    if any(k in lower_name for k in ("sample", "example", "snippet")):
        doc_type = "sample_code"
    if any(k in lower_name for k in ("how-to", "howto", "guide")) and doc_type == "documentation":
        doc_type = "howto"
    if any(k in lower_name for k in ("policy", "policies", "guidelines", "review")):
        domain = "policy"
        doc_type = "policy"
    if any(k in lower_name for k in ("terms", "agreement", "license", "licence")):
        doc_type = "legal"

    # 3. URL-based refinement (current Apple developer site patterns).
    if "/documentation/swift/" in lower_url:
        language = "swift"
        domain = "language_guide"
    if "/documentation/uikit" in lower_url:
        technology = "uikit"
        domain = "framework_guide"
        if product == "unknown":
            product = "ios"
    if "/documentation/swiftui" in lower_url:
        technology = "swiftui"
        domain = "framework_guide"
        if product == "unknown":
            product = "ios"
    if "/documentation/foundation" in lower_url and technology == "unknown":
        technology = "foundation"
        domain = "framework_guide"
    if "/documentation/storekit" in lower_url:
        technology = "storekit"
        domain = "app_store"
        product = "ios"
    if "testflight" in lower_url:
        domain = "app_store"
        product = "ios"
    if "app-store" in lower_url or "/app-store/" in lower_url or "/appstore/" in lower_url:
        domain = "app_store"
        if product == "unknown":
            product = "ios"
    if "/xcode/" in lower_url or "/xcode-playgrounds" in lower_url:
        technology = "xcode"
        domain = "tooling"
        product = "tooling"

    # 4. Section path (logical headings from the markdown).
    if section_path:
        root = (section_path[0] or "").lower()
        if "swift playgrounds" in root:
            technology = "swift_playgrounds"
            domain = "tooling"
            product = "tooling"
        if "testflight" in root:
            domain = "app_store"
            product = "ios"
        if "app store" in root or "appstore" in root:
            domain = "app_store"
            if product == "unknown":
                product = "ios"

    # 5. Text-based heuristics can be added later if really needed; keep this
    # function fast and deterministic for now.

    return {
        "language": language,
        "technology": technology,
        "domain": domain,
        "product": product,
        "doc_type": doc_type,
    }


def _ensure_qdrant_collection(qclient: QdrantClient, dim: int) -> None:
    """Create Qdrant collection if missing; ensure payload indexes; emit human-friendly error if Qdrant is unreachable."""
    # First, try to reach Qdrant and see if the collection exists.
    try:
        qclient.get_collection(RAG_COLLECTION_NAME)
        _ensure_payload_indexes(qclient)
        return
    except ResponseHandlingException as e:
        # Connection-level problem (e.g. Qdrant not running / port closed)
        log("❌ Unable to connect to Qdrant at http://localhost:6333.")
        log("   Make sure Qdrant is running (for example: `docker run -p 6333:6333 qdrant/qdrant`).")
        log("   You can also use `python app.py index --dry-run` to test indexing without Qdrant.")
        log(f"   Underlying error: {e}")
        raise SystemExit(1)
    except Exception:
        # Any other error here likely means the collection is missing; fall through and try to create it.
        pass

    # If we got here, try to create/recreate the collection.
    try:
        qclient.recreate_collection(
            RAG_COLLECTION_NAME,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        log(f"📦 Ensured Qdrant collection '{RAG_COLLECTION_NAME}' (dim={dim})")
        _write_collection_file(RAG_COLLECTION_NAME)
        _ensure_payload_indexes(qclient)
    except ResponseHandlingException as e:
        log("❌ Unable to create Qdrant collection because Qdrant is not reachable at http://localhost:6333.")
        log("   Start Qdrant first (for example: `docker run -p 6333:6333 qdrant/qdrant`),")
        log("   or re-run this command with `--dry-run` to skip writing to Qdrant.")
        log(f"   Underlying error: {e}")
        raise SystemExit(1)
    except Exception as e:
        log(f"❗ Failed to create Qdrant collection '{RAG_COLLECTION_NAME}': {e}")
        raise


def _flush_upsert_batch(qclient: QdrantClient | None, batch: list[PointStruct]) -> None:
    """
    Upsert a batch of points into Qdrant and clear the batch.

    Batching reduces HTTP/API roundtrips significantly when indexing many
    small files, without changing the logical semantics of index_markdown.
    """
    if not batch or qclient is None:
        return
    try:
        qclient.upsert(collection_name=RAG_COLLECTION_NAME, points=batch)
    finally:
        batch.clear()


def _ensure_payload_indexes(qclient: QdrantClient) -> None:
    """
    Ensure payload indexes for frequently used metadata fields.

    Fields:
    - language, technology, domain, product, doc_type: keyword
    - ios_versions, swift_versions: keyword (arrays of strings)

    Index creation is idempotent: if an index already exists, Qdrant will raise,
    which we silently ignore to keep indexing robust.
    """
    index_fields = [
        "language",
        "technology",
        "domain",
        "product",
        "doc_type",
        "ios_versions",
        "swift_versions",
    ]
    for field in index_fields:
        try:
            qclient.create_payload_index(
                collection_name=RAG_COLLECTION_NAME,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            # Already exists or Qdrant rejected this field type; not fatal for indexing.
            continue


def crawl_source(source: dict, dry_run: bool = False) -> None:
    """
    Crawl a configured source:
    - Fetch HTML with crawl4ai
    - Normalize to markdown
    - Update meta.json with content hashes and dirty flags (unless dry_run)
    """
    source_id = source["id"]
    start_url = source["url"]
    max_depth = int(source.get("max_depth", 3))
    start_parsed = urlparse(start_url)
    # Restrict crawl to the first 1–2 path segments of the start URL to avoid
    # wandering across the entire site (e.g. only /documentation/swift/... or
    # /videos/wwdc2024/ for WWDC sessions).
    start_path = (start_parsed.path or "").strip("/")
    start_segments = [s for s in start_path.split("/") if s]
    if start_segments:
        allowed_prefix = "/" + "/".join(start_segments[:2]) + "/"
    else:
        allowed_prefix = "/"

    doc_only = source.get("doc_only", "/documentation/" in (start_parsed.path or ""))
    use_playwright = source.get("crawler") == "playwright" and _HAS_PLAYWRIGHT
    if source.get("crawler") == "playwright" and not _HAS_PLAYWRIGHT:
        log("⚠️ [source={}] Playwright not installed; falling back to Crawl4AI. For code-rich docs run: pip install playwright html2text && playwright install chromium".format(source_id))

    log(
        f"🔍 [source={source_id}] Start deep crawl: {start_url} (max_depth={max_depth})"
        + (" [Playwright]" if use_playwright else " [Crawl4AI]")
        + (" [doc_only]" if doc_only else "")
        + (" [dry-run]" if dry_run else "")
    )
    try:
        if use_playwright:
            results = asyncio.run(
                run_async_crawl_playwright(
                    start_url, max_depth, allowed_prefix, doc_only,
                    extra_seed_urls=source.get("seed_urls") or [],
                )
            )
        else:
            results = asyncio.run(run_async_crawl(start_url, max_depth=max_depth))
    except Exception as e:
        log(f"🔥 Crawler exception for source '{source_id}': {e}")
        return

    total = len(results)
    url_status: dict[str, str] = {}
    ordered_urls: list[str] = []
    for r in results:
        u = getattr(r, "url", None) or "(unknown)"
        ordered_urls.append(u)
        url_status[u] = "failed" if not getattr(r, "success", False) else "queued"

    meta = _load_meta(source_id, start_url)
    pages_meta: dict = meta.get("pages", {})
    _, pages_dir = _source_dirs(source_id)
    if not dry_run:
        _ensure_dir(pages_dir)

    changed_count = 0

    prefix_norm = (allowed_prefix or "/").rstrip("/")
    for i, result in enumerate(results, start=1):
        url = result.url
        if IS_CLI:
            log(f"  Processing [{i}/{total}]: {url}")
        parsed = urlparse(url)
        same_host = parsed.netloc == start_parsed.netloc
        path = (parsed.path or "").rstrip("/")
        if not same_host or not (path == prefix_norm or path.startswith(prefix_norm + "/")):
            log(f"ℹ️ [source={source_id}] [{i}/{total}] Skip non-source URL: {url}")
            url_status[url] = "non_doc"
            cli_progress(f"Crawl {source_id}", i, total)
            continue
        if doc_only and "/documentation" not in (parsed.path or ""):
            log(f"ℹ️ [source={source_id}] [{i}/{total}] Skip non-doc URL (doc_only): {url}")
            url_status[url] = "non_doc"
            cli_progress(f"Crawl {source_id}", i, total)
            continue
        if not result.success:
            log(f"⚠️ [source={source_id}] [{i}/{total}] Failed: {url}")
            url_status[url] = "failed"
            cli_progress(f"Crawl {source_id}", i, total)
            continue
        html = getattr(result, "cleaned_html", None) or getattr(result, "html", "") or ""
        if not html:
            log(f"⛔ [source={source_id}] [{i}/{total}] Empty content: {url}")
            url_status[url] = "empty"
            cli_progress(f"Crawl {source_id}", i, total)
            continue

        # Apple documentation: use RAG-optimized pipeline (fetch -> build -> render).
        if use_playwright and doc_only and "developer.apple.com/documentation" in url:
            try:
                raw = fetch_apple_doc_raw(url)
                page = build_apple_doc_page(raw)
                md = render_apple_doc_to_markdown(page)
            except Exception as e:
                log(f"⚠️ [source={source_id}] [{i}/{total}] Apple pipeline failed for {url}: {e}; fallback to html_to_markdown")
                md = html_to_markdown(html)
        else:
            md = html_to_markdown(html)

        if not md:
            log(f"⚠️ [source={source_id}] [{i}/{total}] Normalized content empty: {url}")
            url_status[url] = "normalized_empty"
            cli_progress(f"Crawl {source_id}", i, total)
            continue

        page_filename = _page_filename_for_url(url)
        page_path = os.path.join(pages_dir, page_filename)
        new_hash = _sha256(md)

        entry = pages_meta.get(page_filename, {})
        old_hash = entry.get("hash")

        if old_hash == new_hash:
            if not IS_CLI:
                log(f"✅ [source={source_id}] [{i}/{total}] Unchanged: {url}")
            url_status[url] = "unchanged"
            cli_progress(f"Crawl {source_id}", i, total)
            continue

        changed_count += 1
        if dry_run:
            if not IS_CLI:
                log(f"📝 [source={source_id}] [{i}/{total}] Would update: {page_filename} [dry-run]")
            url_status[url] = "would_update"
            cli_progress(f"Crawl {source_id}", i, total)
            continue

        try:
            with open(page_path, "w", encoding="utf-8") as f:
                f.write(md)
        except Exception as e:
            log(f"❗ [source={source_id}] [{i}/{total}] Failed to write markdown for {url}: {e}")
            continue

        pages_meta[page_filename] = {
            "url": url,
            "hash": new_hash,
            "last_updated": _now_iso(),
            "dirty": True,
        }
        if not IS_CLI:
            log(f"📝 [source={source_id}] [{i}/{total}] Updated markdown: {page_filename}")
        cli_progress(f"Crawl {source_id}", i, total)

        url_status[url] = "updated"

    if not dry_run:
        meta["pages"] = pages_meta
        meta["last_crawled"] = _now_iso()
        _save_meta(source_id, meta)

    log(
        f"🏁 [source={source_id}] Crawl finished. {total} pages, "
        f"{changed_count} updated/would-update markdown files."
    )

    # В CLI-режиме выводим компактную сводку статусов по URL.
    if IS_CLI and ordered_urls:
        print(f"\n[source={source_id}] URL statuses:")
        for u in ordered_urls:
            st = url_status.get(u, "unknown")
            print(f"  [{st:15}] {u}")


def index_markdown(
    incremental: bool = True,
    source_filter: list[str] | None = None,
    reindex_source_id: str | None = None,
    dry_run: bool = False,
    force_reindex_chunks: bool = False,
) -> None:
    """
    Read markdown from rag_sources and index into Qdrant.
    - incremental=True: only pages with dirty == True (unless reindex_source_id is set)
    - source_filter: only process these source ids; None = all
    - reindex_source_id: treat all pages of this source as dirty
    - dry_run: do not upsert or clear dirty flags
    """
    qclient = QdrantClient(url="http://localhost:6333") if not dry_run else None
    any_indexed = False
    first_dim: int | None = None
    # Сводка по всем "скипнутым" файлам за один проход индексации.
    # Каждый элемент: {"source": ..., "filename": ..., "reason": "...", "details": "..."}.
    skipped_files: list[dict[str, str]] = []
    # Общий батч для upsert в Qdrant (батчим чанки разных файлов).
    upsert_batch: list[PointStruct] = []

    sources = [s for s in SOURCES if source_filter is None or s["id"] in source_filter]
    if not sources:
        log("ℹ️ [index] No sources to index (empty filter?).")
        return

    # Собираем всех кандидатов (source_id, filename, entry, meta, pages_dir)
    candidates: list[tuple[str, str, dict, dict, str]] = []
    excluded_by_filter = 0
    for source in sources:
        source_id = source["id"]
        source_url = source["url"]
        meta = _load_meta(source_id, source_url)
        pages_meta = meta.get("pages", {})
        if not pages_meta:
            continue
        _, pages_dir = _source_dirs(source_id)
        force_dirty = source_id == reindex_source_id
        for filename, entry in pages_meta.items():
            if incremental and not force_dirty and not entry.get("dirty", False):
                continue
            if any(sub in filename for sub in INDEX_EXCLUDE_FILENAME_SUBSTRINGS):
                excluded_by_filter += 1
                skipped_files.append(
                    {
                        "source": source_id,
                        "filename": filename,
                        "reason": "excluded_by_filename_filter",
                    }
                )
                if not dry_run and filename in meta.get("pages", {}):
                    meta["pages"][filename]["dirty"] = False
                    _save_meta(source_id, meta)
                continue
            candidates.append((source_id, filename, entry, meta, pages_dir))

    if excluded_by_filter:
        log(f"ℹ️ [index] Excluded {excluded_by_filter} page(s) by INDEX_EXCLUDE_FILENAME_SUBSTRINGS.")

    if not candidates:
        log("ℹ️ [index] No pages to index.")
        return

    # Deduplication by content hash: same page from multiple runs → index once (prefer apple_documentation)
    by_hash: dict[str, list[tuple[str, str, dict, dict, str]]] = {}
    for c in candidates:
        h = c[2].get("hash") or c[1]
        by_hash.setdefault(h, []).append(c)
    deduplicated: list[tuple[str, str, dict, dict, str]] = []
    skipped_duplicates: list[tuple[str, str, dict]] = []
    for h, items in by_hash.items():
        items_sorted = sorted(items, key=lambda x: (0 if x[0] == "apple_documentation" else 1, x[0]))
        keep = items_sorted[0]
        deduplicated.append(keep)
        for dup in items_sorted[1:]:
            skipped_duplicates.append((dup[0], dup[1], dup[3]))

    if skipped_duplicates:
        log(f"ℹ️ [index] Skipping {len(skipped_duplicates)} duplicate page(s) (same content in another source).")
        for sid, fname, m in skipped_duplicates:
            if IS_CLI:
                log(f"  skip duplicate: {sid}/pages/{fname}")
            if not dry_run and fname in m.get("pages", {}):
                m["pages"][fname]["dirty"] = False
                _save_meta(sid, m)

    total_pages = len(deduplicated)
    log(
        f"📚 [index] {total_pages} page(s) to index (after dedup)"
        + (" [dry-run]" if dry_run else "")
    )

    for idx, (source_id, filename, entry, meta, pages_dir) in enumerate(deduplicated, start=1):
        log(f"[{idx}/{total_pages}] [index] Processing {source_id}/pages/{filename}")
        page_path = os.path.join(pages_dir, filename)
        try:
            with open(page_path, "r", encoding="utf-8") as f:
                md = f.read()
        except Exception as e:
            log(f"❗ [index] Failed to read {page_path}: {e}")
            skipped_files.append(
                {
                    "source": source_id,
                    "filename": filename,
                    "reason": "read_error",
                    "details": str(e),
                }
            )
            continue

        md = _strip_markdown_boilerplate(md)
        md = _normalize_markdown_whitespace(md)
        head = md[:INDEX_EXCLUDE_CONTENT_HEAD_CHARS]
        if any(sub in head for sub in INDEX_EXCLUDE_CONTENT_SUBSTRINGS):
            log(f"ℹ️ [index] Skipping promo content (DEVELOPER STORIES): {source_id}/pages/{filename}")
            if not dry_run and filename in meta.get("pages", {}):
                meta["pages"][filename]["dirty"] = False
                _save_meta(source_id, meta)
            continue

        chunks_with_paths = _split_markdown_into_chunks(
            md, max_chunk_size=CHUNK_MAX_SIZE, min_chunk_size=CHUNK_MIN_SIZE
        )
        if not chunks_with_paths:
            log(f"⚠️ [index] No chunks produced for {filename}")
            skipped_files.append(
                {
                    "source": source_id,
                    "filename": filename,
                    "reason": "no_chunks",
                }
            )
            continue

        chunk_texts = [t for t, _ in chunks_with_paths]
        embeddings = get_embeddings(chunk_texts)
        if not embeddings:
            log(f"❌ [index] No embeddings for {filename}, skipping")
            skipped_files.append(
                {
                    "source": source_id,
                    "filename": filename,
                    "reason": "no_embeddings",
                }
            )
            continue

        dim = len(embeddings[0])
        if first_dim is None:
            first_dim = dim
            if not dry_run and qclient is not None:
                _ensure_qdrant_collection(qclient, first_dim)

        if dim != first_dim:
            log(
                f"❗ [index] Dimension mismatch for {filename}: "
                f"got {dim}, expected {first_dim}. Skipping this file."
            )
            log(
                "   Hint: if you changed the embedding model (RAG_EMBED_MODEL) "
                "and its vector dimension, run `python app.py rebuild` to "
                "recreate the Qdrant collection with the new dim."
            )
            skipped_files.append(
                {
                    "source": source_id,
                    "filename": filename,
                    "reason": "dimension_mismatch",
                }
            )
            continue

        # --- Chunk-level diff: upsert only new/changed chunks, delete gone ones. ---
        old_chunk_hashes: list[str] = entry.get("chunk_hashes") or []
        if force_reindex_chunks:
            # При полном rebuild коллекция в Qdrant пустая, поэтому игнорируем
            # кеш chunk_hashes из meta.json и переиндексируем все чанки.
            old_chunk_hashes = []
        old_hash_set = set(old_chunk_hashes)
        new_chunk_hashes: list[str] = []
        points_to_upsert: list[PointStruct] = []

        for local_idx, ((chunk_text, section_path), vec) in enumerate(
            zip(chunks_with_paths, embeddings)
        ):
            section_path_str = ":".join(section_path) if section_path else ""
            # Stable, content-based chunk id:
            # - source_id / filename / section_path_str фиксируют "место" в доке
            # - полный chunk_text фиксирует содержимое чанка
            # При вставке/удалении абзацев вокруг, но без изменения самого текста
            # чанка, его hash (и, следовательно, point id) останется прежним.
            chunk_hash = _sha256(
                f"{source_id}:{filename}:{section_path_str}:{chunk_text}"
            )
            new_chunk_hashes.append(chunk_hash)

            if chunk_hash in old_hash_set:
                # Чанк уже есть в индексе и контент не изменился — повторно не upsert'им.
                continue

            point_id = _point_id_from_hash(chunk_hash)
            ios_versions, swift_versions = _extract_versions(chunk_text)
            meta_extra = infer_metadata(
                source_id=source_id,
                filename=filename,
                url=entry.get("url"),
                section_path=section_path,
                text=chunk_text,
            )
            payload = {
                "source": source_id,
                "url": entry.get("url"),
                "path": f"pages/{filename}",
                "chunk_id": chunk_hash,
                "text": chunk_text,
                "section_path": section_path,
                "ios_versions": ios_versions,
                "swift_versions": swift_versions,
                "version": meta.get("last_crawled"),
                **meta_extra,
            }
            points_to_upsert.append(
                PointStruct(
                    id=point_id,
                    vector=vec,
                    payload=payload,
                )
            )

        # Чанки, которые были раньше, но исчезли из новой версии страницы.
        new_hash_set = set(new_chunk_hashes)
        hashes_to_delete = old_hash_set - new_hash_set
        ids_to_delete = [_point_id_from_hash(h) for h in hashes_to_delete] if hashes_to_delete else []

        num_upserts = len(points_to_upsert)
        num_deletes = len(ids_to_delete)

        if dry_run:
            if num_upserts or num_deletes:
                log(
                    f"📥 [index] [dry-run] Source '{source_id}' file '{filename}': "
                    f"would upsert {num_upserts} vector(s), delete {num_deletes} old vector(s)"
                )
                any_indexed = True
            else:
                log(
                    f"📥 [index] [dry-run] Source '{source_id}' file '{filename}': "
                    f"no changes at chunk level"
                )
            continue

        # Реальный режим: сначала удаляем "лишние" чанки, затем upsert'им новые/изменённые.
        try:
            if ids_to_delete and qclient is not None:
                qclient.delete(
                    collection_name=RAG_COLLECTION_NAME,
                    points_selector=PointIdsList(points=ids_to_delete),
                    wait=True,
                )

            if points_to_upsert:
                upsert_batch.extend(points_to_upsert)
                if len(upsert_batch) >= BATCH_UPSERT_SIZE:
                    _flush_upsert_batch(qclient, upsert_batch)

            # Обновляем метаданные страницы: новые chunk_hashes и сбрасываем dirty.
            if filename in meta.get("pages", {}):
                meta["pages"][filename]["dirty"] = False
                meta["pages"][filename]["chunk_hashes"] = new_chunk_hashes
            _save_meta(source_id, meta)

            if num_upserts or num_deletes:
                any_indexed = True
                ts = datetime.now().strftime("%H:%M:%S")
                log(
                    f"📥 [{ts}] [index] Source '{source_id}' file '{filename}': "
                    f"upserted {num_upserts} vector(s), deleted {num_deletes} old vector(s)"
                )
            else:
                ts = datetime.now().strftime("%H:%M:%S")
                log(
                    f"📥 [{ts}] [index] Source '{source_id}' file '{filename}': "
                    f"no changes at chunk level"
                )

        except Exception as e:
            log(
                f"❗ [index] Qdrant upsert/delete error for source '{source_id}', "
                f"file '{filename}': {e}"
            )
            skipped_files.append(
                {
                    "source": source_id,
                    "filename": filename,
                    "reason": "upsert_error",
                    "details": str(e),
                }
            )

    # Финальный сброс батча upsert'ов (если что‑то осталось).
    if upsert_batch and not dry_run:
        _flush_upsert_batch(qclient, upsert_batch)

    if any_indexed and not dry_run:
        _write_collection_file(RAG_COLLECTION_NAME)
        log("✅ [index] Indexing completed.")
    elif any_indexed and dry_run:
        log("✅ [index] Dry-run completed (no writes).")
    else:
        log("ℹ️ [index] Nothing was indexed.")

    # В конце — компактный массив скипнутых файлов (для отладки качества индекса).
    if skipped_files:
        try:
            log("ℹ️ [index] Skipped files (JSON array):")
            log(json.dumps(skipped_files, ensure_ascii=False, indent=2))
        except Exception:
            log(
                f"ℹ️ [index] Skipped {len(skipped_files)} file(s); "
                "see previous log messages for detailed reasons."
            )


def rebuild_qdrant(dry_run: bool = False) -> None:
    """Drop the dev_docs collection and re-index all markdown pages from scratch."""
    if dry_run:
        log(f"🧨 [rebuild] [dry-run] Would drop collection '{RAG_COLLECTION_NAME}' and re-index all")
        index_markdown(incremental=False, dry_run=True, force_reindex_chunks=True)
        return
    qclient = QdrantClient(url="http://localhost:6333")
    log(f"🧨 [rebuild] Dropping collection '{RAG_COLLECTION_NAME}'")
    try:
        qclient.delete_collection(RAG_COLLECTION_NAME)
    except Exception as e:
        log(f"⚠️ [rebuild] Failed to delete collection (may not exist): {e}")

    index_markdown(incremental=False, force_reindex_chunks=True)


def run_crawl_all_sources(
    source_filter: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """Crawl configured sources and update local markdown store."""
    sources = [s for s in SOURCES if source_filter is None or s["id"] in source_filter]
    if not sources:
        log("ℹ️ No sources to crawl (empty filter?).")
        return
    log("🚀 Starting crawl for " + (f"sources {[s['id'] for s in sources]}" if source_filter else "all configured sources") + (" [dry-run]" if dry_run else ""))
    for source in sources:
        crawl_source(source, dry_run=dry_run)
    log("🏁 All sources crawled.")


def run_index_all_sources(
    incremental: bool = True,
    source_filter: list[str] | None = None,
    reindex_source: str | None = None,
    dry_run: bool = False,
) -> None:
    """Index markdown from sources into Qdrant."""
    log(
        f"🚀 Starting index (incremental={incremental})"
        + (f" sources={source_filter}" if source_filter else " all sources")
        + (f" reindex_source={reindex_source}" if reindex_source else "")
        + (" [dry-run]" if dry_run else "")
    )
    index_markdown(
        incremental=incremental,
        source_filter=source_filter,
        reindex_source_id=reindex_source,
        dry_run=dry_run,
    )
    log("🏁 Index step finished.")


def run_rebuild_all(dry_run: bool = False) -> None:
    """Rebuild Qdrant collection from local markdown store."""
    log("🚀 Starting full rebuild of Qdrant from markdown store" + (" [dry-run]" if dry_run else ""))
    rebuild_qdrant(dry_run=dry_run)
    log("🏁 Rebuild finished.")


def do_crawl(start_url):
    global stop_flag, id_counter
    try:
        # Legacy one-off crawl directly into Qdrant (kept for backward compatibility).
        # New, recommended flow:
        #   python app.py crawl   -> update rag_sources markdown store
        #   python app.py index   -> index dirty pages into Qdrant
        #   python app.py rebuild -> drop + full re-index
        results = asyncio.run(run_async_crawl(start_url))
        total = len(results)
        log(f"✅ [1/4] Crawl finished. {total} pages found.")

        qclient = QdrantClient(url="http://localhost:6333")
        coll = collection_name_from_url(start_url)
        _write_collection_file(coll)
        log(f"📦 Collection: {coll}")
        created = False

        for i, result in enumerate(results):
            idx = i + 1
            if not result.success:
                log(f"⚠️ [{idx}/{total}] Failed: {result.url}")
                continue

            url = result.url
            log(f"📄 [{idx}/{total}] [2/4] Processing: {url}")

            html = getattr(result, "cleaned_html", None) or getattr(result, "html", "") or ""
            if not html:
                log(f"⛔ [{idx}/{total}] Empty content")
                continue

            splitter = HTMLSemanticPreservingSplitter(
                headers_to_split_on=[('h1','h1'), ('h2','h2'), ('h3','h3')],
                max_chunk_size=1000
            )
            docs = splitter.split_text(html)
            texts = [doc.page_content for doc in docs]

            if not texts:
                log(f"⚠️ [{idx}/{total}] No chunks generated")
                continue

            log(f"✂️ [{idx}/{total}] [3/4] Chunks: {len(texts)}")
            embeddings = get_embeddings(texts)
            if not embeddings:
                log(f"❌ [{idx}/{total}] No embeddings, skipping")
                continue

            if not created:
                dim = len(embeddings[0])
                try:
                    qclient.recreate_collection(coll, vectors_config=VectorParams(size=dim, distance=Distance.COSINE))
                    log(f"📦 Created Qdrant collection '{coll}' (dim={dim})")
                except Exception as e:
                    log(f"❗ Qdrant creation error: {e}")
                created = True

            points = [PointStruct(id=id_counter + j, vector=vec, payload={"url": url, "text": texts[j]}) for j, vec in enumerate(embeddings)]
            id_counter += len(points)

            try:
                qclient.upsert(collection_name=coll, points=points)
                log(f"📥 [{idx}/{total}] [4/4] Indexed {len(points)} vectors")
            except Exception as e:
                log(f"❗ Qdrant insert error: {e}")

    except Exception as e:
        log(f"🔥 Crawler exception: {e}")
    finally:
        stop_flag = True
        log("🏁 Done.")

if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="RAG pipeline: crawl → markdown store → index → Qdrant"
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["crawl", "index", "rebuild", "update"],
        help=(
            "crawl: update markdown store; "
            "index: index dirty pages; "
            "rebuild: drop + full re-index; "
            "update: crawl then index"
        ),
    )
    parser.add_argument(
        "--source",
        action="append",
        dest="sources",
        metavar="SOURCE_ID",
        help="Limit to source id (e.g. apple_documentation). Can be repeated.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Crawl/index/rebuild without writing (crawl: no md/meta; index: no upsert; rebuild: no delete/index).",
    )
    parser.add_argument(
        "--reindex-source",
        metavar="SOURCE_ID",
        help="(index only) Treat all pages of this source as dirty and re-index them.",
    )
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    # CLI режим: включаем прогресс-бары и отключаем накопление SSE-лога
    IS_CLI = True

    source_list = args.sources if args.sources else None
    if args.command == "crawl":
        run_crawl_all_sources(source_filter=source_list, dry_run=args.dry_run)
    elif args.command == "index":
        run_index_all_sources(
            incremental=True,
            source_filter=source_list,
            reindex_source=args.reindex_source,
            dry_run=args.dry_run,
        )
    elif args.command == "rebuild":
        run_rebuild_all(dry_run=args.dry_run)
    elif args.command == "update":
        # Полный цикл: crawl (инкрементальный по контенту) → index (инкрементальный по dirty-страницам)
        run_crawl_all_sources(source_filter=source_list, dry_run=args.dry_run)
        run_index_all_sources(
            incremental=True,
            source_filter=source_list,
            reindex_source=args.reindex_source,
            dry_run=args.dry_run,
        )
    else:
        parser.print_help()
        sys.exit(1)