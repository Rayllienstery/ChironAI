from flask import Flask, request, Response
import os
import re
import sys
import threading

# Project root (for domain/config) when running from WebUI.
_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)
import asyncio
import concurrent.futures
import time
import json
import hashlib
from datetime import datetime, timezone
from typing import Callable
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

# Executor for running fetch_apple_doc_raw in a thread when called from inside asyncio (crawl callback).
# Avoids "coroutine was never awaited" / nested asyncio.run().
_apple_fetch_executor: concurrent.futures.ThreadPoolExecutor | None = None


def _fetch_apple_doc_raw_safe(url: str):
    """Call fetch_apple_doc_raw; run in thread if we're inside a running event loop."""
    global _apple_fetch_executor
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return fetch_apple_doc_raw(url)
    if _apple_fetch_executor is None:
        _apple_fetch_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
    return _apple_fetch_executor.submit(fetch_apple_doc_raw, url).result()

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

from domain.services.chunking import (
    CHUNK_MAX_SIZE,
    CHUNK_MIN_SIZE,
    chunk_quality_ok,
    split_markdown_into_chunks,
)
from domain.services.markdown_meta import parse_and_strip_meta_block
from domain.services.metadata_inference import (
    build_embed_prefix,
    estimate_token_count,
    extract_versions,
    infer_chunk_display_meta,
    infer_metadata,
)


app = Flask(__name__)

# Register shared WebUI API (status, RAG, Ollama, Open WebUI, crawler, etc.)
from api.http.webui_routes import webui_bp
app.register_blueprint(webui_bp)

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

# Load SOURCES from YAML config file
def _load_sources_from_yaml() -> list[dict]:
    """Load crawl sources from config/sources.yaml."""
    try:
        from pathlib import Path
        try:
            import yaml
        except ImportError:
            # Fallback if yaml not available
            return _get_default_sources()
        
        # Try to find config directory relative to project root
        project_root = Path(BASE_DIR).parent
        config_path = project_root / "config" / "sources.yaml"
        
        if not config_path.is_file():
            # Fallback: use default hardcoded source
            return _get_default_sources()
        
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        sources = data.get("sources", [])
        # Ensure seed_urls is always a list
        for source in sources:
            if "seed_urls" not in source:
                source["seed_urls"] = []
            elif not isinstance(source["seed_urls"], list):
                source["seed_urls"] = []
        
        return sources if sources else _get_default_sources()
    except Exception as e:
        # Use print since log() may not be defined during module import
        print(f"⚠️ Failed to load sources from YAML: {e}, using default", file=sys.stderr)
        return _get_default_sources()


def _get_default_sources() -> list[dict]:
    """Return default hardcoded source configuration."""
    return [
        {
            "id": "apple_documentation",
            "url": "https://developer.apple.com/documentation",
            "max_depth": 2,
            "crawler": "playwright",
            "doc_only": True,
            "seed_urls": [],
        }
    ]


def _save_sources_to_yaml(sources: list[dict]) -> bool:
    """Save crawl sources to config/sources.yaml. Returns True on success."""
    try:
        from pathlib import Path
        try:
            import yaml
        except ImportError:
            return False
        
        project_root = Path(BASE_DIR).parent
        config_path = project_root / "config" / "sources.yaml"
        
        # Ensure config directory exists
        config_path.parent.mkdir(parents=True, exist_ok=True)
        
        data = {"sources": sources}
        with config_path.open("w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        return True
    except Exception as e:
        # Use print since this may be called before log() is available
        print(f"❌ Failed to save sources to YAML: {e}", file=sys.stderr)
        return False


# Load sources on module import
SOURCES = _load_sources_from_yaml()

# # Single-URL SOURCES for pipeline parity test (app.py vs app_tester.py)
# SOURCES = [
#     {
#         "id": "apple_documentation",
#         "url": "https://developer.apple.com/documentation",
#         "max_depth": 1,
#         "crawler": "playwright",
#         "doc_only": True,
#         "seed_urls": [
#             "https://developer.apple.com/documentation/swiftui/view",
#         ],
#     },
# ]

# Ограничение по корневым префиксам фреймворков: краулим только то, что реально нужно под задачи разработки.
FRAMEWORK_ROOT_PREFIXES = [
    "/documentation/swift",
    "/documentation/swift/concurrency",
    "/documentation/swiftui",
    "/documentation/uikit",
    "/documentation/appkit",
    "/documentation/foundation",
    "/documentation/combine",
    "/documentation/tvuikit",
    "/documentation/watchkit",
    "/documentation/webkit",
    "/documentation/widgetkit",
    "/documentation/uniformtypeidentifiers",
    "/documentation/usernotifications",
    "/documentation/usernotificationsui",
    "/documentation/vision",
    "/documentation/visionkit",
    "/documentation/weatherkit",
    "/documentation/weatherkitrestapi",
    "/documentation/passkit",
    "/documentation/walletorders",
    "/documentation/workoutkit",
    "/documentation/coredata",
    "/documentation/cloudkit",
    "/documentation/xctest",
    "/documentation/xcuiautomation",
    "/documentation/xcode",
    "/documentation/xcodecloud",
    "/documentation/xcodekit",
    "/documentation/xcselect",
    "/documentation/watchconnectivity",
    "/documentation/xpc",
    # Условно полезные, но оставляем как корни
    "/documentation/videotoolbox",
    "/documentation/virtualization",
    "/documentation/wifiaware",
    "/documentation/wi_fi_infrastructure",
    "/documentation/visionos",
    "/documentation/visualintelligence",
    "/documentation/webkitjs",
    "/documentation/backgroundtasks",
    "/documentation/network",
]

# Пути, которые считаем низкоценными для RAG и исключаем на этапе краулинга.
EXCLUDED_PATH_SUBSTRINGS = [
    "/release-notes",
    "/wwdc",
    "/topics/",
    "/collections/",
]

# Crawl speed and rate-limit: parallel fetches, single goto per URL, retry on 429.
CRAWL_CONCURRENCY = 6
CRAWL_GOTO_TIMEOUT_MS = 30000
# Short wait after domcontentloaded so Apple Docs SPA can render nav/sidebar links (otherwise we discover no child pages).
CRAWL_DOM_READY_WAIT_MS = 2500
CRAWL_MAX_RETRIES_429 = 3
CRAWL_BACKOFF_BASE_SEC = 2  # exponential backoff: 2^attempt seconds, capped
CRAWL_BACKOFF_MAX_SEC = 60

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
    # WWDC highlights/overview hubs (каталоги ссылок, не техдока)
    "wwdc2021",
    "wwdc2022",
    "wwdc2023",
    "wwdc2024",
    "wwdc2025",
]

# Если в начале markdown (первые N символов) есть одна из этих подстрок — страницу не индексируем (промо/шоукейс).
# Skip indexing files with almost no engineering content (e.g. stub API refs, hub pages).
INDEX_MIN_CONTENT_LENGTH = 400  # chars of body content (after meta/strip) below this → skip

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
                # Try to detect language from class attribute or content
                lang = ""
                if code_el is not None:
                    code_class = code_el.get("class", "") or ""
                    if "swift" in code_class.lower():
                        lang = "swift"
                    elif "objective-c" in code_class.lower() or "objc" in code_class.lower():
                        lang = "objectivec"
                # Fallback: detect Swift by common patterns
                if not lang and ("import " in raw or "func " in raw or "class " in raw or "let " in raw or "var " in raw):
                    lang = "swift"
                lang_suffix = lang if lang else ""
                out.append(f"\n\n```{lang_suffix}\n{raw}\n```\n\n")
        elif tag == "div":
            raw = (el.text_content() or "").strip()
            if raw and len(raw) > 2:
                # Only treat as code if it looks like code (has code-like structure)
                # Avoid wrapping entire page content in code block
                div_class = el.get("class", "") or ""
                is_code_div = any(keyword in div_class.lower() for keyword in ["code", "snippet", "sample", "example"])
                has_code_structure = any(pattern in raw for pattern in ["import ", "func ", "class ", "let ", "var ", "{", "}", "()"])
                
                if is_code_div or (has_code_structure and len(raw) < 5000):  # Reasonable code block size
                    lang = ""
                    if "swift" in div_class.lower():
                        lang = "swift"
                    elif "objective-c" in div_class.lower() or "objc" in div_class.lower():
                        lang = "objectivec"
                    elif not lang and has_code_structure:
                        lang = "swift"  # Default for Apple docs
                    lang_suffix = lang if lang else ""
                    out.append(f"\n\n```{lang_suffix}\n{raw}\n```\n\n")
                else:
                    # Regular div content, not code
                    out.append(raw + "\n\n")
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


# Default section headings to strip; overridden by config index noise_section_headings.
_DEFAULT_NOISE_SECTIONS = [
    "conforming types",
    "inherited by",
    "inherits from",
    "relationships",
]


def _get_noise_sections() -> frozenset[str]:
    """Noise section headings from config (normalized lower); fallback to default list."""
    try:
        from config import get_indexing_list  # type: ignore
        raw = get_indexing_list("noise_section_headings", _DEFAULT_NOISE_SECTIONS)
        return frozenset((s.strip().lower() for s in raw if s and isinstance(s, str)))
    except Exception:
        return frozenset(_DEFAULT_NOISE_SECTIONS)


def _strip_noise_sections(md: str) -> str:
    """
    Remove noise sections from markdown at index time.
    These autogenerated blocks (Conforming Types, Inherited By, Inherits From, Relationships)
    add embedding noise and dominate tokens without adding engineering value for RAG.
    Match is by normalized heading: equals or starts-with (handles "Conforming Types (Condition)", trailing spaces).
    """
    if not md:
        return ""
    lines = md.split("\n")
    out: list[str] = []
    skip = False
    noise = _get_noise_sections()
    for ln in lines:
        stripped = ln.strip()
        if stripped.startswith("#"):
            heading = re.sub(r"^#+\s*", "", stripped).strip().lower()
            if any(
                heading == n or heading.startswith(n + " ") or heading.startswith(n + "(")
                for n in noise
            ):
                skip = True
                continue
            skip = False
        if skip:
            continue
        out.append(ln)
    text = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


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


def _crawl_url_allowed(
    url: str,
    depth: int,
    max_depth: int,
    start_parsed,
    base_url: str,
    prefix_p: str,
    doc_only: bool,
    visited: set[str],
) -> bool:
    """Return True if (url, depth) should be crawled."""
    if url in visited or depth > max_depth:
        return False
    parsed = urlparse(url)
    if parsed.netloc != start_parsed.netloc:
        return False
    path_p = (parsed.path or "").rstrip("/")
    if not (path_p == prefix_p or path_p.startswith(prefix_p + "/")):
        return False
    if doc_only and "/documentation" not in (parsed.path or ""):
        return False
    if any(sub in path_p.lower() for sub in EXCLUDED_PATH_SUBSTRINGS):
        return False
    if not any(path_p == root or path_p.startswith(root + "/") for root in FRAMEWORK_ROOT_PREFIXES):
        return False
    return True


async def _fetch_one_url(
    browser,
    url: str,
    depth: int,
    semaphore: asyncio.Semaphore,
    base_url: str,
    start_parsed,
    prefix_p: str,
    doc_only: bool,
) -> tuple[_CrawlResult, list[str]]:
    """
    Single goto per URL: domcontentloaded only, no networkidle.
    On same page: get body HTML and links. Retry on 429 with backoff (and Retry-After).
    Returns (result, list of absolute link URLs).
    """
    async with semaphore:
        for attempt in range(CRAWL_MAX_RETRIES_429):
            page = None
            try:
                page = await browser.new_page()
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=CRAWL_GOTO_TIMEOUT_MS,
                )
                if response and response.status == 429:
                    retry_after = response.headers.get("retry-after", "").strip()
                    wait_sec = CRAWL_BACKOFF_MAX_SEC
                    if retry_after.isdigit():
                        wait_sec = min(int(retry_after), CRAWL_BACKOFF_MAX_SEC)
                    else:
                        wait_sec = min(
                            CRAWL_BACKOFF_BASE_SEC ** attempt,
                            CRAWL_BACKOFF_MAX_SEC,
                        )
                    await page.close()
                    page = None
                    log(f"  ⚠️ 429 for {url}, retry in {wait_sec}s (attempt {attempt + 1}/{CRAWL_MAX_RETRIES_429})")
                    await asyncio.sleep(wait_sec)
                    continue
                break
            except Exception:
                if page:
                    await page.close()
                if attempt + 1 >= CRAWL_MAX_RETRIES_429:
                    return _CrawlResult(url, False, ""), []
                await asyncio.sleep(min(CRAWL_BACKOFF_BASE_SEC ** attempt, CRAWL_BACKOFF_MAX_SEC))
                continue

        if not page:
            return _CrawlResult(url, False, ""), []

        # Let Apple Docs SPA render nav/sidebar so link extraction finds child pages.
        try:
            await asyncio.sleep(CRAWL_DOM_READY_WAIT_MS / 1000.0)
        except Exception:
            pass

        try:
            body = await page.evaluate("""() => {
                const main = document.querySelector('main') || document.querySelector('article') || document.body;
                return main ? main.innerHTML : document.body.innerHTML;
            }""")
        except Exception:
            body = ""
        try:
            links = await page.evaluate("""() => {
                const seen = new Set();
                const out = [];
                function add(h) {
                    if (h && (h.startsWith('http') || h.startsWith('/')) && !seen.has(h)) {
                        seen.add(h);
                        out.push(h);
                    }
                }
                [document.querySelector('main'), document.querySelector('aside'), document.querySelector('nav')]
                    .filter(Boolean).forEach(root => {
                        if (root) root.querySelectorAll('a[href]').forEach(a => add(a.getAttribute('href')));
                    });
                document.querySelectorAll('a[href]').forEach(a => add(a.getAttribute('href')));
                return out;
            }""")
        except Exception:
            links = []
        await page.close()

        if not body:
            return _CrawlResult(url, False, ""), links if isinstance(links, list) else []

        full_html = f"<!DOCTYPE html><html><head></head><body>{body}</body></html>"
        result = _CrawlResult(url, True, full_html)

        absolute_links: list[str] = []
        for raw in (links if isinstance(links, list) else []):
            href = (raw or "").split("#")[0].strip()
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
            absolute_links.append(next_url)

        return result, absolute_links


async def run_async_crawl_playwright(
    start_url: str,
    max_depth: int,
    allowed_prefix: str,
    doc_only: bool,
    extra_seed_urls: list[str] | None = None,
    on_page_processed: Callable[[_CrawlResult], None] | None = None,
) -> list:
    """
    BFS crawl using Playwright. Single goto per URL (domcontentloaded only, no networkidle).
    Parallel fetches with CRAWL_CONCURRENCY. Retry on 429 with backoff and Retry-After.
    Returns list of _CrawlResult(url, success, html).
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
    semaphore = asyncio.Semaphore(CRAWL_CONCURRENCY)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            while queue:
                batch: list[tuple[str, int]] = []
                while len(batch) < CRAWL_CONCURRENCY and queue:
                    url, depth = queue.pop(0)
                    if not _crawl_url_allowed(
                        url, depth, max_depth, start_parsed, base_url, prefix_p, doc_only, visited
                    ):
                        continue
                    visited.add(url)
                    batch.append((url, depth))

                if not batch:
                    continue

                for url, depth in batch:
                    log(f"  Fetching [depth {depth}]: {url}")

                tasks = [
                    _fetch_one_url(
                        browser, url, depth, semaphore, base_url, start_parsed, prefix_p, doc_only
                    )
                    for url, depth in batch
                ]
                batch_results = await asyncio.gather(*tasks, return_exceptions=True)

                for (url, depth), outcome in zip(batch, batch_results):
                    if isinstance(outcome, BaseException):
                        results.append(_CrawlResult(url, False, ""))
                        if on_page_processed:
                            on_page_processed(_CrawlResult(url, False, ""))
                        continue
                    result, absolute_links = outcome
                    results.append(result)
                    if on_page_processed:
                        on_page_processed(result)
                    if depth >= max_depth:
                        continue
                    for next_url in absolute_links:
                        try:
                            next_parsed = urlparse(next_url)
                            if next_parsed.netloc != start_parsed.netloc:
                                continue
                            next_path = (next_parsed.path or "").rstrip("/")
                            if not (next_path == prefix_p or next_path.startswith(prefix_p + "/")):
                                continue
                            if doc_only and "/documentation" not in (next_parsed.path or ""):
                                continue
                            if any(sub in next_path.lower() for sub in EXCLUDED_PATH_SUBSTRINGS):
                                continue
                            if not any(
                                next_path == root or next_path.startswith(root + "/")
                                for root in FRAMEWORK_ROOT_PREFIXES
                            ):
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
# Qdrant upsert batch size (points). We batch vectors across files to reduce
# HTTP roundtrips while keeping memory usage predictable.
BATCH_UPSERT_SIZE = 200


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
        "doc_scope",
        "ios_versions",
        "swift_versions",
        "symbol",
        "framework",
        "section",
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
    
    # Initialize metadata and directories before crawl
    meta = _load_meta(source_id, start_url)
    pages_meta: dict = meta.get("pages", {})
    _, pages_dir = _source_dirs(source_id)
    if not dry_run:
        _ensure_dir(pages_dir)
    
    # Use seed_urls from meta.json if available, otherwise from source dict
    seed_urls = meta.get("seed_urls") or source.get("seed_urls") or []
    
    changed_count = 0
    url_status: dict[str, str] = {}
    ordered_urls: list[str] = []
    processed_urls: set[str] = set()  # Track URLs processed by callback
    prefix_norm = (allowed_prefix or "/").rstrip("/")
    
    def process_single_page(result: _CrawlResult, is_callback: bool = False) -> bool:
        """
        Process a single crawl result: convert to markdown and save file.
        Returns True if page was processed (saved or skipped), False if should be skipped.
        """
        nonlocal changed_count, pages_meta
        
        url = result.url
        parsed = urlparse(url)
        same_host = parsed.netloc == start_parsed.netloc
        path = (parsed.path or "").rstrip("/")
        
        # Filter checks
        if not same_host or not (path == prefix_norm or path.startswith(prefix_norm + "/")):
            if not is_callback:
                url_status[url] = "non_doc"
            return False
        # Только /documentation/ если doc_only
        if doc_only and "/documentation" not in (parsed.path or ""):
            if not is_callback:
                url_status[url] = "non_doc"
            return False
        # Исключаем низкоценные разделы (release-notes, WWDC, topics, collections)
        if any(sub in path.lower() for sub in EXCLUDED_PATH_SUBSTRINGS):
            if not is_callback:
                url_status[url] = "non_doc"
            return False
        # Ограничиваемся только нужными корневыми префиксами фреймворков
        if not any(path == root or path.startswith(root + "/") for root in FRAMEWORK_ROOT_PREFIXES):
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
        
        # Convert to markdown — same pipeline as app_tester: Apple only, no fallback
        if use_playwright and doc_only and "developer.apple.com/documentation" in url:
            try:
                raw = _fetch_apple_doc_raw_safe(url)
                page = build_apple_doc_page(raw)
                md = render_apple_doc_to_markdown(page)
            except Exception as e:
                if not is_callback:
                    log(f"⚠️ [source={source_id}] Apple pipeline failed for {url}: {e}; skipping (no fallback)")
                return False
        else:
            md = html_to_markdown(html)
        
        # Validation: detect if markdown is wrapped in a single code block (bad conversion)
        md_stripped = md.strip() if md else ""
        if md_stripped and md_stripped.startswith("```") and md_stripped.endswith("```"):
            # Count code fences - if only 2 (start and end), entire content is in one code block
            fence_count = md_stripped.count("```")
            if fence_count == 2:
                # This is a broken conversion - entire page wrapped in code block
                if not is_callback:
                    log(f"⚠️ [source={source_id}] Markdown wrapped in single code block for {url}; this indicates fallback conversion issue")
                # Mark as problematic - will be excluded from indexing if needed
        
        if not md:
            if not is_callback:
                url_status[url] = "normalized_empty"
            return False
        
        page_filename = _page_filename_for_url(url)
        page_path = os.path.join(pages_dir, page_filename)
        new_hash = _sha256(md)
        
        entry = pages_meta.get(page_filename, {})
        old_hash = entry.get("hash")
        
        if old_hash == new_hash:
            if not is_callback:
                if not IS_CLI:
                    log(f"✅ [source={source_id}] Unchanged: {url}")
                url_status[url] = "unchanged"
            return True
        
        changed_count += 1
        if dry_run:
            if not is_callback:
                if not IS_CLI:
                    log(f"📝 [source={source_id}] Would update: {page_filename} [dry-run]")
                url_status[url] = "would_update"
            return True
        
        # Save file immediately
        try:
            with open(page_path, "w", encoding="utf-8") as f:
                f.write(md)
        except Exception as e:
            if not is_callback:
                log(f"❗ [source={source_id}] Failed to write markdown for {url}: {e}")
            return False
        
        pages_meta[page_filename] = {
            "url": url,
            "hash": new_hash,
            "last_updated": _now_iso(),
            "dirty": True,
        }
        
        if not is_callback:
            if not IS_CLI:
                log(f"📝 [source={source_id}] Updated markdown: {page_filename}")
            url_status[url] = "updated"
        else:
            # Periodic meta.json save during crawl (every 10 pages)
            if changed_count % 10 == 0:
                meta["pages"] = pages_meta
                _save_meta(source_id, meta)
        
        return True
    
    # Callback for immediate file saving during crawl
    def on_page_callback(result: _CrawlResult) -> None:
        """Called immediately after each page is fetched during crawl."""
        url = result.url
        if url not in processed_urls:
            processed_urls.add(url)
            process_single_page(result, is_callback=True)
    
    try:
        if use_playwright:
            results = asyncio.run(
                run_async_crawl_playwright(
                    start_url, max_depth, allowed_prefix, doc_only,
                    extra_seed_urls=seed_urls,
                    on_page_processed=on_page_callback if not dry_run else None,
                )
            )
        else:
            results = asyncio.run(run_async_crawl(start_url, max_depth=max_depth))
    except Exception as e:
        log(f"🔥 Crawler exception for source '{source_id}': {e}")
        return

    total = len(results)
    for r in results:
        u = getattr(r, "url", None) or "(unknown)"
        if u not in ordered_urls:
            ordered_urls.append(u)
        if u not in url_status:
            url_status[u] = "failed" if not getattr(r, "success", False) else "queued"

    # Process any remaining results that weren't processed by callback
    # (for non-playwright crawler or if callback wasn't used)
    for i, result in enumerate(results, start=1):
        url = result.url
        if IS_CLI:
            log(f"  Processing [{i}/{total}]: {url}")
        
        # Skip if already processed by callback
        if url in processed_urls:
            cli_progress(f"Crawl {source_id}", i, total)
            continue
        
        # Process the result
        processed = process_single_page(result, is_callback=False)
        cli_progress(f"Crawl {source_id}", i, total)

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

        # Validation: skip files wrapped in a single code block (broken conversion)
        md_stripped = md.strip()
        if md_stripped.startswith("```") and md_stripped.endswith("```"):
            fence_count = md_stripped.count("```")
            if fence_count == 2:
                log(f"ℹ️ [index] Skipping file wrapped in single code block (broken conversion): {source_id}/pages/{filename}")
                skipped_files.append(
                    {
                        "source": source_id,
                        "filename": filename,
                        "reason": "wrapped_in_code_block",
                        "details": "Entire markdown wrapped in single code fence - indicates fallback conversion failure",
                    }
                )
                if not dry_run and filename in meta.get("pages", {}):
                    meta["pages"][filename]["dirty"] = False
                    _save_meta(source_id, meta)
                continue

        page_meta, md = parse_and_strip_meta_block(md)
        md = _strip_markdown_boilerplate(md)
        md = _normalize_markdown_whitespace(md)
        md = _strip_noise_sections(md)
        if len(md.strip()) < INDEX_MIN_CONTENT_LENGTH:
            log(f"ℹ️ [index] Skipping minimal content (body < {INDEX_MIN_CONTENT_LENGTH} chars): {source_id}/pages/{filename}")
            skipped_files.append(
                {
                    "source": source_id,
                    "filename": filename,
                    "reason": "minimal_content",
                    "details": f"Body content length {len(md.strip())} < {INDEX_MIN_CONTENT_LENGTH}",
                }
            )
            if not dry_run and filename in meta.get("pages", {}):
                meta["pages"][filename]["dirty"] = False
                _save_meta(source_id, meta)
            continue
        head = md[:INDEX_EXCLUDE_CONTENT_HEAD_CHARS]
        if any(sub in head for sub in INDEX_EXCLUDE_CONTENT_SUBSTRINGS):
            log(f"ℹ️ [index] Skipping promo content (DEVELOPER STORIES): {source_id}/pages/{filename}")
            if not dry_run and filename in meta.get("pages", {}):
                meta["pages"][filename]["dirty"] = False
                _save_meta(source_id, meta)
            continue

        chunks_with_paths = split_markdown_into_chunks(
            md, max_chunk_size=CHUNK_MAX_SIZE, min_chunk_size=CHUNK_MIN_SIZE
        )
        chunks_with_paths = [(t, p) for t, p in chunks_with_paths if chunk_quality_ok(t)]
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
        embed_texts = [
            build_embed_prefix(page_meta, sp) + t
            for t, sp in chunks_with_paths
        ]
        embeddings = get_embeddings(embed_texts)
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
            ios_versions, swift_versions = extract_versions(chunk_text)
            if page_meta.get("ios_versions"):
                ios_versions = sorted(set(ios_versions + page_meta["ios_versions"]))
            if page_meta.get("swift_versions"):
                swift_versions = sorted(set(swift_versions + page_meta["swift_versions"]))
            url_for_meta = page_meta.get("url") or entry.get("url")
            meta_extra = infer_metadata(
                source_id=source_id,
                filename=filename,
                url=url_for_meta,
                section_path=section_path,
                text=chunk_text,
            )
            if page_meta.get("framework"):
                meta_extra["technology"] = page_meta["framework"].lower()
            if page_meta.get("doc_kind"):
                meta_extra["doc_type"] = page_meta["doc_kind"]
            if page_meta.get("doc_scope"):
                meta_extra["doc_scope"] = page_meta["doc_scope"]
            display_meta = infer_chunk_display_meta(section_path)
            payload = {
                "source": source_id,
                "url": url_for_meta or entry.get("url", ""),
                "path": f"pages/{filename}",
                "chunk_id": chunk_hash,
                "text": chunk_text,
                "section_path": section_path,
                "ios_versions": ios_versions,
                "swift_versions": swift_versions,
                "version": meta.get("last_crawled"),
                **meta_extra,
            }
            if page_meta.get("framework"):
                payload["framework"] = page_meta["framework"]
            if display_meta.get("symbol"):
                payload["symbol"] = display_meta["symbol"]
            if display_meta.get("section"):
                payload["section"] = display_meta["section"]
            payload["token_count"] = estimate_token_count(chunk_text)
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
        description="RAG pipeline: crawl → markdown store → index → Qdrant; or start WebUI."
    )
    parser.add_argument(
        "command",
        nargs="?",
        choices=["start", "crawl", "index", "rebuild", "update"],
        help=(
            "start: run WebUI (Flask); "
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

    if args.command == "start":
        from config import get_webui_port
        port = get_webui_port()
        app.run(host="0.0.0.0", port=port)
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