from flask import Flask
import os
import re
import sys

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
from typing import Any, Callable
import requests
from urllib.parse import urlparse

import csv

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

from domain.services.markdown_meta import parse_and_strip_meta_block

try:
    from modules.md_indexer import get_active_pipeline_name, run_pipeline as run_md_indexer_pipeline
except ImportError:
    get_active_pipeline_name = None
    run_md_indexer_pipeline = None
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
        print(f"WARNING: Failed to load sources from YAML: {e}, using default", file=sys.stderr)
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
        print(f"ERROR: Failed to save sources to YAML: {e}", file=sys.stderr)
        return False


# Load sources on module import
SOURCES = _load_sources_from_yaml()

# Default path allowlist/excludelist (used when crawler.yaml is missing or for per-source fallback).
_DEFAULT_FRAMEWORK_ROOT_PREFIXES = [
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
_DEFAULT_EXCLUDED_PATH_SUBSTRINGS = [
    "/release-notes",
    "/wwdc",
    "/topics/",
    "/collections/",
]


def _load_crawler_config() -> tuple[list[str], list[str]]:
    """Load framework_root_prefixes and excluded_path_substrings from config/crawler.yaml. Fallback to defaults."""
    try:
        from pathlib import Path
        import yaml
        project_root = Path(BASE_DIR).parent
        config_path = project_root / "config" / "crawler.yaml"
        if not config_path.is_file():
            return _DEFAULT_FRAMEWORK_ROOT_PREFIXES, _DEFAULT_EXCLUDED_PATH_SUBSTRINGS
        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        crawler = data.get("crawler") or {}
        prefixes = crawler.get("framework_root_prefixes")
        excluded = crawler.get("excluded_path_substrings")
        return (
            list(prefixes) if isinstance(prefixes, list) else _DEFAULT_FRAMEWORK_ROOT_PREFIXES,
            list(excluded) if isinstance(excluded, list) else _DEFAULT_EXCLUDED_PATH_SUBSTRINGS,
        )
    except Exception:
        return _DEFAULT_FRAMEWORK_ROOT_PREFIXES, _DEFAULT_EXCLUDED_PATH_SUBSTRINGS


FRAMEWORK_ROOT_PREFIXES, EXCLUDED_PATH_SUBSTRINGS = _load_crawler_config()

# Crawl speed and rate-limit: parallel fetches, single goto per URL, retry on 429.
CRAWL_CONCURRENCY = 6
CRAWL_GOTO_TIMEOUT_MS = 30000
# Short wait after domcontentloaded so Apple Docs SPA can render nav/sidebar links (otherwise we discover no child pages).
CRAWL_DOM_READY_WAIT_MS = 2500
CRAWL_MAX_RETRIES_429 = 3
CRAWL_BACKOFF_BASE_SEC = 2  # exponential backoff: 2^attempt seconds, capped
CRAWL_BACKOFF_MAX_SEC = 60

# Swift Book (docs.swift.org) filtering: allowlist/denylist of chapter slugs.
SWIFT_BOOK_ALLOWED_SLUGS: set[str] = {
    "thebasics",
    "basicoperators",
    "stringsandcharacters",
    "collectiontypes",
    "controlflow",
    "functions",
    "closures",
    "enumerations",
    "structuresandclasses",
    "properties",
    "methods",
    "subscripts",
    "inheritance",
    "initialization",
    "deinitialization",
    "optionalchaining",
    "errorhandling",
    "concurrency",
    "macros",
    "typecasting",
    "nestedtypes",
    "extensions",
    "protocols",
    "generics",
    "opaquetypes",
    "automaticreferencecounting",
    "memorysafety",
    "accesscontrol",
    "advancedoperators",
    "lexicalstructure",
    "types",
    "expressions",
    "statements",
    "declarations",
    "attributes",
    "patterns",
    "genericparametersandarguments",
    "summaryofthegrammar",
}

SWIFT_BOOK_EXCLUDED_SLUGS: set[str] = {
    "aboutswift",
    "compatibility",
    "guidedtour",
    "aboutthelanguagereference",
    "revisionhistory",
    # Book table-of-contents is allowed as a valid slug.
}


def log(message: str) -> None:
    """Append message to in-memory log queue and print to stdout."""
    print(message)
    # In CLI mode SSE logging is not used, so we don't need to grow the queue.
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

def _ensure_dir(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
            log(f"WARNING: Failed to read meta.json for {source_id}: {e}")
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
        log(f" Failed to write meta.json for {source_id}: {e}")


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


def _parse_wwdc_event_year(event: str) -> int | None:
    """
    Parse WWDC event label like 'WWDC24' or 'WWDC2024' into a four-digit year.
    Returns None when parsing fails.
    """
    if not event:
        return None
    event = event.strip().upper()
    if not event.startswith("WWDC"):
        return None
    suffix = event[4:]
    if not suffix.isdigit():
        return None
    if len(suffix) == 2:
        year = 2000 + int(suffix)
    else:
        year = int(suffix)
    return year


def _extract_wwdc_session_id_from_url(url: str) -> tuple[int | None, str | None]:
    """
    Extract (year, session_id) from Apple transcript URL when possible.
    Examples of expected patterns:
      .../wwdc2024/wwdc2024-10136-transcript-eng.json
    """
    try:
        parsed = urlparse(url)
        path = parsed.path or ""
    except Exception:
        return None, None
    m = re.search(r"wwdc(\d{4})-(\d+)-transcript", path)
    if not m:
        return None, None
    year = int(m.group(1))
    session_id = m.group(2)
    return year, session_id


def _flatten_wwdc_transcript_json(data) -> list[dict[str, str | None]]:
    """
    Conservatively flatten WWDC transcript JSON into an ordered list of segments.
    Each segment is a dict with optional 'speaker' and 'text' keys.

    The JSON schema for WWDC transcripts is not formally documented here, so this
    helper favours robustness over strict structure: it walks lists/dicts in
    document order and captures any nodes that look like speech segments.
    """
    segments: list[dict[str, str | None]] = []

    def visit(node):
        # Newer WWDC JSON format: transcript is a list of [timecode, text] pairs.
        if isinstance(node, list):
            # Handle flat [time, text] entries directly.
            if (
                len(node) >= 2
                and isinstance(node[0], (int, float))
                and isinstance(node[1], str)
            ):
                cleaned = " ".join(node[1].split())
                if cleaned:
                    segments.append({"speaker": None, "text": cleaned})
                return
            # Otherwise, recurse into list items.
            for item in node:
                visit(item)
            return

        if isinstance(node, dict):
            text = None
            speaker = None
            # Common field names we might care about
            for key, value in node.items():
                kl = str(key).lower()
                if isinstance(value, str):
                    if kl in ("text", "body", "caption", "utterance"):
                        # Prefer the first text-like field we see
                        if text is None:
                            text = value
                    elif kl in ("speaker", "name", "presenter"):
                        speaker = value
            if text:
                cleaned = " ".join(text.split())
                if cleaned:
                    segments.append({"speaker": speaker, "text": cleaned})
            # Recurse into children to keep document order
            for v in node.values():
                visit(v)

    visit(data)
    # Simple de-duplication of consecutive duplicate text segments
    deduped: list[dict[str, str | None]] = []
    last_text: str | None = None
    for seg in segments:
        text = seg.get("text") or ""
        if not text or text == last_text:
            continue
        last_text = text
        deduped.append(seg)
    return deduped


def _wwdc_segments_to_markdown(
    *,
    url: str,
    event: str,
    year: int | None,
    session_id: str | None,
    title: str,
    segments: list[dict[str, str | None]],
) -> str:
    """
    Render WWDC transcript segments to RAG-optimized markdown.
    - Meta block at the top with event/year/session_id.
    - H1 title.
    - Speaker-labelled paragraphs where possible.

    Applies WWDC-specific "fluff" filtering to aggressively drop
    non-technical one-liners (thanks, promos, cross-promo, music notes)
    before building paragraphs.
    """
    lines: list[str] = []

    # Purely polite / marketing / reaction sentences that carry no technical value.
    _FLUFF_SENTENCES: set[str] = {
        # Thanks / goodbyes
        "thanks for joining me",
        "thank you for joining me",
        "thank you for watching",
        "thanks for watching",
        "thank you for watching and goodbye",
        "thank you, and see you around",
        "thank you and see you around",
        "see you around",
        "see you next time",
        "thank you",
        # Short reactions
        "that's so cool",
        "ooh, shiny",
        "yeah. it was a big day",
        "it was a big day",
        # Promo taglines
        "seventeen big and little things from apple wwdc23",
        "get all the updates on apple.com",
    }

    # Sentence-level prefixes that usually indicate pure promo / cross‑promo
    # or non-technical guidance (case-insensitive, applied after strip).
    _FLUFF_PREFIXES: tuple[str, ...] = (
        "for more information",
        "for more details",
        "to learn more",
        "to learn how",
        "to learn more about",
        "check out ",
        "be sure to watch",
        "get all the updates on",
        "our entire team is incredibly thrilled",
        "we hope that",
        "we hope you'll",
        "i hope they will",
    )

    _sentence_split_re = re.compile(r"(?<=[.!?])\s+")

    def _strip_wwdc_fluff_from_text(text: str) -> str:
        """
        Remove WWDC-specific fluff sentences from a segment text while
        preserving technical content (APIs, frameworks, patterns).
        """
        if not text:
            return ""
        parts = _sentence_split_re.split(text)
        kept: list[str] = []
        for raw in parts:
            s = " ".join(raw.strip().split())
            if not s:
                continue
            norm = s.lower()
            norm_stripped = norm.rstrip(".!?:\"'“”")
            # Exact-match fluff sentences.
            if norm_stripped in _FLUFF_SENTENCES:
                continue
            # Cross‑promo / marketing boilerplate by prefix.
            if any(norm_stripped.startswith(p) for p in _FLUFF_PREFIXES):
                continue
            # Purely musical / soundtrack annotations.
            if "♪" in s:
                continue
            kept.append(s)
        return " ".join(kept)

    lines.append("<!--")
    lines.append("meta:")
    lines.append(f"  url: {url}")
    lines.append(f"  event: {event}")
    if year is not None:
        lines.append(f"  year: {year}")
    if session_id is not None:
        lines.append(f"  session_id: {session_id}")
    lines.append("  doc_kind: wwdc_session")
    lines.append("-->")
    lines.append("")

    lines.append(f"# {title}")
    lines.append("")

    if year is not None or session_id is not None:
        meta_parts: list[str] = []
        if year is not None:
            meta_parts.append(str(year))
        meta_parts.append(event)
        if session_id is not None:
            meta_parts.append(f"Session {session_id}")
        lines.append(" · ".join(meta_parts))
        lines.append("")

    current_speaker: str | None = None
    current_text_parts: list[str] = []

    def flush_paragraph():
        nonlocal current_speaker, current_text_parts
        if not current_text_parts:
            return
        para = " ".join(" ".join(current_text_parts).split())
        if not para:
            current_text_parts = []
            return
        if current_speaker:
            lines.append(f"**{current_speaker}:** {para}")
        else:
            lines.append(para)
        lines.append("")
        current_text_parts = []

    for seg in segments:
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        # Aggressively strip WWDC-specific promo / thanks / music fluff
        # at sentence level while keeping technical sentences.
        text = _strip_wwdc_fluff_from_text(text)
        if not text:
            continue
        speaker = seg.get("speaker")
        # Tiny filler tokens are noise for RAG; skip them.
        if len(text) <= 3 and text.lower() in {"um", "uh", "so"}:
            continue
        if speaker != current_speaker and current_text_parts:
            flush_paragraph()
        current_speaker = speaker
        current_text_parts.append(text)

    flush_paragraph()

    md = "\n".join(lines)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    if run_md_indexer_pipeline is not None and get_active_pipeline_name is not None:
        _, md = run_md_indexer_pipeline(get_active_pipeline_name(), md)
    return md


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
        # If among ancestors there is another "content" block, do not treat this element as top-level.
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


def _apply_markdown_cleanup_pipeline(md: str) -> tuple[dict[str, Any], str]:
    """
    Apply config-driven MD cleanup pipeline (md_indexer). Returns (page_meta, processed_body).
    Fallback to parse_and_strip_meta_block only if md_indexer is not available.
    """
    if run_md_indexer_pipeline is not None and get_active_pipeline_name is not None:
        return run_md_indexer_pipeline(get_active_pipeline_name(), md)
    page_meta, body = parse_and_strip_meta_block(md)
    return (page_meta, body)


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
    if run_md_indexer_pipeline is not None and get_active_pipeline_name is not None:
        _, body = run_md_indexer_pipeline(get_active_pipeline_name(), raw)
        return body
    return re.sub(r"\n{3,}", "\n\n", raw.strip())


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
    else:
        raw = _html_to_markdown_regex(html)
    if run_md_indexer_pipeline is not None and get_active_pipeline_name is not None:
        _, body = run_md_indexer_pipeline(get_active_pipeline_name(), raw)
        return body
    return re.sub(r"\n{3,}", "\n\n", raw.strip())


def _crawl_wwdc_transcripts_source(source: dict, dry_run: bool = False) -> None:
    """
    Crawl WWDC transcript index (TSV + JSON) and write markdown pages under rag_sources.

    Expected source.extra fields:
      - type: wwdc_transcripts
      - tsv_url: URL to WWDC-Transcripts-2014-2024-ENG.tsv
      - min_year: minimum event year (e.g. 2019) to include
    """
    source_id = source["id"]
    extra = source.get("extra") or {}
    tsv_url = extra.get(
        "tsv_url",
        "https://gist.githubusercontent.com/elkraneo/6015e04c81dd227dd9974a2ec9d89cff/raw/WWDC-Transcripts-2014-2024-ENG.tsv",
    )
    min_year = int(extra.get("min_year", 2019))

    log(
        f"[source={source_id}] Fetching WWDC transcript index from TSV: {tsv_url} "
        + (f"(min_year={min_year})" if min_year else "")
        + (" [dry-run]" if dry_run else "")
    )

    try:
        resp = requests.get(tsv_url, timeout=60)
        resp.raise_for_status()
        tsv_text = resp.text
    except Exception as e:
        log(f"ERROR: [source={source_id}] Failed to download TSV index: {e}")
        return

    # Prepare storage
    start_url = source.get("url", tsv_url)
    meta = _load_meta(source_id, start_url)
    pages_meta: dict = meta.get("pages", {})
    _, pages_dir = _source_dirs(source_id)
    if not dry_run:
        _ensure_dir(pages_dir)

    # Parse TSV rows
    reader = csv.DictReader(tsv_text.splitlines(), delimiter="\t")
    rows: list[dict[str, str]] = []
    for row in reader:
        event = (row.get("Event") or "").strip()
        link = (row.get("Link") or "").strip()
        title = (row.get("Transcript Name") or "").strip()
        if not event or not link or not title:
            continue
        year = _parse_wwdc_event_year(event)
        if year is None or (min_year and year < min_year):
            continue
        rows.append(
            {
                "event": event,
                "year": str(year),
                "link": link,
                "title": title,
            }
        )

    if not rows:
        log(f"[source={source_id}] No WWDC rows matched filter (min_year={min_year}); nothing to do.")
        return

    log(f"[source={source_id}] {len(rows)} WWDC transcript(s) to process from TSV.")

    changed_count = 0

    for idx, row in enumerate(rows, start=1):
        event = row["event"]
        year = int(row["year"])
        transcript_url = row["link"]
        title = row["title"] or f"{event} session"

        log(f"[source={source_id}] [{idx}/{len(rows)}] Fetching transcript JSON: {transcript_url}")

        try:
            resp = requests.get(transcript_url, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            log(f"ERROR: [source={source_id}] Failed to fetch/parse JSON for {transcript_url}: {e}")
            continue

        segments = _flatten_wwdc_transcript_json(data)
        if not segments:
            log(f"[source={source_id}] Skipping empty transcript for {transcript_url}")
            continue

        session_year_from_url, session_id = _extract_wwdc_session_id_from_url(transcript_url)
        # Prefer year derived from event label; URL-based year is only a fallback
        effective_year = year or session_year_from_url

        md = _wwdc_segments_to_markdown(
            url=transcript_url,
            event=event,
            year=effective_year,
            session_id=session_id,
            title=title,
            segments=segments,
        )

        page_filename = _page_filename_for_url(transcript_url)
        page_path = os.path.join(pages_dir, page_filename)
        new_hash = _sha256(md)

        entry = pages_meta.get(page_filename, {})
        old_hash = entry.get("hash")

        if old_hash == new_hash:
            log(f"[source={source_id}] Unchanged WWDC transcript: {page_filename}")
            continue

        changed_count += 1
        if dry_run:
            log(f"[source={source_id}] Would update WWDC transcript: {page_filename} [dry-run]")
            continue

        try:
            with open(page_path, "w", encoding="utf-8") as f:
                f.write(md)
        except Exception as e:
            log(f"ERROR: [source={source_id}] Failed to write markdown for WWDC transcript {transcript_url}: {e}")
            continue

        pages_meta[page_filename] = {
            "url": transcript_url,
            "hash": new_hash,
            "last_updated": _now_iso(),
        }

        log(f"[source={source_id}] Updated WWDC transcript markdown: {page_filename}")

    if not dry_run:
        meta["pages"] = pages_meta
        meta["last_crawled"] = _now_iso()
        _save_meta(source_id, meta)

    log(
        f"[source={source_id}] WWDC transcript crawl complete. "
        f"Changed pages: {changed_count}"
        + (" [dry-run]" if dry_run else "")
    )


class _CrawlResult:
    """Minimal result object (url, success, html)."""

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
    allowed_path_prefixes: list[str] | None = None,
    excluded_path_substrings: list[str] | None = None,
) -> bool:
    """Return True if (url, depth) should be crawled. When provided, use per-source lists; else globals."""
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
    excluded = excluded_path_substrings if excluded_path_substrings is not None else EXCLUDED_PATH_SUBSTRINGS
    if any(sub in path_p.lower() for sub in excluded):
        return False
    roots = allowed_path_prefixes if allowed_path_prefixes is not None else FRAMEWORK_ROOT_PREFIXES
    # Normalize roots so that both '/foo/bar' and '/foo/bar/' work the same way.
    for root in roots:
        r = (root or "").rstrip("/")
        if not r:
            continue
        if path_p == r or path_p.startswith(r + "/"):
            return True
    return False


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
                    log(f"  WARNING: 429 for {url}, retry in {wait_sec}s (attempt {attempt + 1}/{CRAWL_MAX_RETRIES_429})")
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
    allowed_path_prefixes: list[str] | None = None,
    excluded_path_substrings: list[str] | None = None,
) -> list:
    """
    BFS crawl using Playwright. Single goto per URL (domcontentloaded only, no networkidle).
    Parallel fetches with CRAWL_CONCURRENCY. Retry on 429 with backoff and Retry-After.
    When provided, allowed_path_prefixes and excluded_path_substrings override globals for this run.
    Returns list of _CrawlResult(url, success, html).
    """
    if not _HAS_PLAYWRIGHT:
        log("WARNING: Playwright not installed; run: pip install playwright && playwright install chromium")
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
    excluded = excluded_path_substrings if excluded_path_substrings is not None else EXCLUDED_PATH_SUBSTRINGS
    roots = allowed_path_prefixes if allowed_path_prefixes is not None else FRAMEWORK_ROOT_PREFIXES

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            while queue:
                batch: list[tuple[str, int]] = []
                while len(batch) < CRAWL_CONCURRENCY and queue:
                    url, depth = queue.pop(0)
                    if not _crawl_url_allowed(
                        url, depth, max_depth, start_parsed, base_url, prefix_p, doc_only, visited,
                        allowed_path_prefixes=allowed_path_prefixes,
                        excluded_path_substrings=excluded_path_substrings,
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
                            if any(sub in next_path.lower() for sub in excluded):
                                continue
                            if not any(next_path == root or next_path.startswith(root + "/") for root in roots):
                                continue
                            if next_url not in visited:
                                queue.append((next_url, depth + 1))
                        except Exception:
                            pass
        finally:
            await browser.close()
    return results


def crawl_source(source: dict, dry_run: bool = False) -> None:
    """
    Crawl a configured source:
    - Fetch HTML with Playwright
    - Normalize to markdown
    - Update meta.json with content hashes (unless dry_run)
    """
    source_id = source["id"]

    # WWDC transcripts sources are handled via a dedicated JSON/TSV pipeline,
    # not the generic Playwright crawler.
    extra = source.get("extra") or {}
    if extra.get("type") == "wwdc_transcripts":
        _crawl_wwdc_transcripts_source(source, dry_run=dry_run)
        return

    if source.get("crawler") != "playwright":
        log("[source={}] Only Playwright crawler is supported; skipping.".format(source_id))
        return
    if not _HAS_PLAYWRIGHT:
        log("[source={}] Playwright is required. Run: pip install playwright html2text && playwright install chromium".format(source_id))
        return

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
    # Per-source URL allowlist; when not set, use globals from crawler config.
    effective_path_prefixes = source.get("path_prefixes") or FRAMEWORK_ROOT_PREFIXES
    effective_excluded = source.get("excluded_path_substrings") or EXCLUDED_PATH_SUBSTRINGS

    log(
        f"[source={source_id}] Start deep crawl: {start_url} (max_depth={max_depth}) [Playwright]"
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
        # Only /documentation/ when doc_only (for swift_book doc_only = False)
        if doc_only and "/documentation" not in (parsed.path or ""):
            if not is_callback:
                url_status[url] = "non_doc"
            return False
        # Exclude low-value sections (release-notes, WWDC, topics, collections)
        if any(sub in path.lower() for sub in effective_excluded):
            if not is_callback:
                url_status[url] = "non_doc"
            return False
        # Swift Book: filter chapters by slug
        if source_id == "swift_book":
            slug = path.split("/")[-1] if path else ""
            if slug in SWIFT_BOOK_EXCLUDED_SLUGS:
                if not is_callback:
                    url_status[url] = "non_doc"
                return False
            if SWIFT_BOOK_ALLOWED_SLUGS and slug not in SWIFT_BOOK_ALLOWED_SLUGS and slug != "the-swift-programming-language":
                if not is_callback:
                    url_status[url] = "non_doc"
                return False
        # Limit to allowed framework root prefixes
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
        
        # Convert to markdown — same pipeline as app_tester: Apple only, no fallback
        if _HAS_PLAYWRIGHT and doc_only and "developer.apple.com/documentation" in url:
            try:
                raw = _fetch_apple_doc_raw_safe(url)
                page = build_apple_doc_page(raw)
                md = render_apple_doc_to_markdown(page)
            except Exception as e:
                if not is_callback:
                    log(f"WARNING: [source={source_id}] Apple pipeline failed for {url}: {e}; skipping (no fallback)")
                return False
        else:
            md = html_to_markdown(html)

        # Unified cleanup pipeline for all sources (same as for Apple docs / index).
        _, md = _apply_markdown_cleanup_pipeline(md)

        # Validation: detect if markdown is wrapped in a single code block (bad conversion)
        md_stripped = md.strip() if md else ""
        if md_stripped and md_stripped.startswith("```") and md_stripped.endswith("```"):
            # Count code fences - if only 2 (start and end), entire content is in one code block
            fence_count = md_stripped.count("```")
            if fence_count == 2:
                # This is a broken conversion - entire page wrapped in code block
                if not is_callback:
                    log(f"WARNING: [source={source_id}] Markdown wrapped in single code block for {url}; this indicates fallback conversion issue")
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
                    log(f"[source={source_id}] Unchanged: {url}")
                url_status[url] = "unchanged"
            return True
        
        changed_count += 1
        if dry_run:
            if not is_callback:
                if not IS_CLI:
                    log(f"[source={source_id}] Would update: {page_filename} [dry-run]")
                url_status[url] = "would_update"
            return True
        
        # Save file immediately
        try:
            with open(page_path, "w", encoding="utf-8") as f:
                f.write(md)
        except Exception as e:
            if not is_callback:
                log(f"ERROR: [source={source_id}] Failed to write markdown for {url}: {e}")
            return False
        
        pages_meta[page_filename] = {
            "url": url,
            "hash": new_hash,
            "last_updated": _now_iso(),
        }
        
        if not is_callback:
            if not IS_CLI:
                log(f"[source={source_id}] Updated markdown: {page_filename}")
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
        results = asyncio.run(
            run_async_crawl_playwright(
                start_url, max_depth, allowed_prefix, doc_only,
                extra_seed_urls=seed_urls,
                on_page_processed=on_page_callback if not dry_run else None,
                allowed_path_prefixes=effective_path_prefixes,
                excluded_path_substrings=effective_excluded,
            )
        )
    except Exception as e:
        log(f"ERROR: Crawler exception for source '{source_id}': {e}")
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
        process_single_page(result, is_callback=False)
        cli_progress(f"Crawl {source_id}", i, total)

    if not dry_run:
        meta["pages"] = pages_meta
        meta["last_crawled"] = _now_iso()
        _save_meta(source_id, meta)

    log(
        f"[source={source_id}] Crawl finished. {total} pages, "
        f"{changed_count} updated/would-update markdown files."
    )

    # In CLI mode, print a compact status summary by URL.
    if IS_CLI and ordered_urls:
        print(f"\n[source={source_id}] URL statuses:")
        for u in ordered_urls:
            st = url_status.get(u, "unknown")
            print(f"  [{st:15}] {u}")


def run_crawl_all_sources(
    source_filter: list[str] | None = None,
    dry_run: bool = False,
) -> None:
    """Crawl configured sources and update local markdown store."""
    sources = [s for s in SOURCES if source_filter is None or s["id"] in source_filter]
    if not sources:
        log("No sources to crawl (empty filter?).")
        return
    log(
        "Starting crawl for "
        + (f"sources {[s['id'] for s in sources]}" if source_filter else "all configured sources")
        + (" [dry-run]" if dry_run else "")
    )
    for source in sources:
        crawl_source(source, dry_run=dry_run)
    log("All sources crawled.")


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="WebUI server or crawl: update local markdown store under rag_sources."
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
        help="Limit to source id (e.g. apple_documentation). Can be repeated. Omit to crawl all.",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        dest="crawl_all",
        help="Crawl all configured sources (same as omitting --source).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Crawl without writing md/meta.",
    )
    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    if args.command == "start":
        import logging

        from config import get_webui_port

        logging.getLogger("werkzeug").setLevel(logging.WARNING)
        port = get_webui_port()
        app.run(host="0.0.0.0", port=port)
        sys.exit(0)

    # CLI mode: enable progress bars and disable SSE log accumulation
    IS_CLI = True

    source_list = None if getattr(args, "crawl_all", False) else (args.sources if args.sources else None)
    if args.command == "crawl":
        run_crawl_all_sources(source_filter=source_list, dry_run=args.dry_run)
    else:
        parser.print_help()
        sys.exit(1)