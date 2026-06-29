"""Fetch missing Apple doc gap pages into Core/data/webui/rag_sources/apple_documentation."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "Core"))
sys.path.insert(0, os.path.join(ROOT, "CoreModules", "WebUIBackend"))
sys.path.insert(0, os.path.join(ROOT, "Core", "modules", "crawler_service"))

from crawler_service.application.crawl_runner import page_filename_for_url  # noqa: E402

from core.webui_data_paths import resolve_webui_data_dir  # noqa: E402
from webui_backend.apple_docs_extract import (  # noqa: E402
    build_apple_doc_page,
    render_apple_doc_to_markdown,
)
from webui_backend.apple_docs_fetcher import fetch_apple_doc_raw  # noqa: E402

GAP_URLS = [
    "https://developer.apple.com/documentation/observation",
    "https://developer.apple.com/documentation/swiftui/observable",
    "https://developer.apple.com/documentation/swift/concurrency",
]
SOURCE_ID = "apple_documentation"


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def main() -> int:
    webui_dir = resolve_webui_data_dir(Path(ROOT))
    meta_path = webui_dir / "rag_sources" / SOURCE_ID / "meta.json"
    pages_dir = webui_dir / "rag_sources" / SOURCE_ID / "pages"
    os.makedirs(pages_dir, exist_ok=True)

    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)
    pages = meta.setdefault("pages", {})

    for url in GAP_URLS:
        print(f"Fetching {url} ...")
        raw = fetch_apple_doc_raw(url)
        page = build_apple_doc_page(raw)
        md = render_apple_doc_to_markdown(page)
        filename = page_filename_for_url(url)
        path = os.path.join(pages_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(md)
        entry = pages.setdefault(filename, {})
        entry["url"] = url
        entry["hash"] = _sha256(md)
        entry["last_updated"] = _now_iso()
        for key in ("framework", "doc_kind", "doc_scope"):
            val = None
            if key == "framework":
                val = page.framework
            elif key == "doc_kind":
                val = page.doc_kind
            elif key == "doc_scope":
                from webui_backend.apple_docs_extract import _doc_scope_for_doc_kind

                val = _doc_scope_for_doc_kind(page.doc_kind)
            if val:
                entry[key] = val
        entry.pop("chunk_hashes", None)
        print(f"  -> {filename} ({len(md)} bytes)")

    meta["last_crawled"] = _now_iso()
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
