#!/usr/bin/env python3
"""
Offline audit: run prepare_markdown_for_indexing + chunk stats on curated Apple Documentation pages.

Expects repo root as cwd (or set CHIRON_ROOT). Reads WebUI/rag_sources/apple_documentation/meta.json + pages/.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Curated URL path fragments -> representative Apple docs for RAG quality review
GOLDEN_URL_FRAGMENTS: tuple[str, ...] = (
    "/documentation/swiftui/view",
    "/documentation/swiftui",
    "/documentation/swiftui/declaring-a-custom-view",
    "/documentation/swiftui/configuring-views",
    "/documentation/swiftui/displaying-data-in-lists",
    "/documentation/swiftui/migrating-to-the-swiftui-life-cycle",
    "/documentation/swiftui/reducing-view-modifier-maintenance",
    "/documentation/swiftui/state",
    "/documentation/swiftui/observable",
    "/documentation/swift/concurrency",
    "/documentation/swift/async-await",
    "/documentation/observation",
    "/documentation/uikit/uiapplication",
    "/documentation/appkit/nsapplication",
    "/documentation/combine",
    "/documentation/foundation/urlsession",
    "/documentation/xctest",
    "/documentation/swiftui/app",
    "/documentation/swiftui/scene",
    "/documentation/swiftui/windowgroup",
)


def _repo_root() -> Path:
    env = os.environ.get("CHIRON_ROOT", "").strip()
    if env:
        return Path(env).resolve()
    return Path(__file__).resolve().parent.parent


def _resolve_pages(meta_path: Path) -> list[tuple[str, str]]:
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    pages = meta.get("pages") or {}
    found: list[tuple[str, str]] = []
    used_files: set[str] = set()
    for frag in GOLDEN_URL_FRAGMENTS:
        for fname, entry in pages.items():
            if fname in used_files:
                continue
            url = (entry or {}).get("url") or ""
            if frag in url:
                found.append((fname, url))
                used_files.add(fname)
                break
    return found


def main() -> int:
    root = _repo_root()
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "CoreModules" / "MdIngestionService"))

    from domain.services.chunking import chunk_quality_ok, split_markdown_into_chunks
    from config import get_indexing_int
    from md_ingestion_service.domain.services.indexing_prepare import prepare_markdown_for_indexing

    meta_path = root / "WebUI" / "rag_sources" / "apple_documentation" / "meta.json"
    pages_dir = root / "WebUI" / "rag_sources" / "apple_documentation" / "pages"
    if not meta_path.is_file():
        print(f"meta.json not found: {meta_path}", file=sys.stderr)
        return 1
    if not pages_dir.is_dir():
        print(f"pages dir not found: {pages_dir}", file=sys.stderr)
        return 1

    pairs = _resolve_pages(meta_path)
    max_sz = get_indexing_int("chunk_max_size", 1200)
    min_sz = get_indexing_int("chunk_min_size", 300)

    print(f"Resolved {len(pairs)} pages (golden fragments matched).\n")
    for fname, url in pairs:
        path = pages_dir / fname
        raw = path.read_text(encoding="utf-8")
        prep = prepare_markdown_for_indexing(fname, raw)
        if prep.skipped:
            print(f"SKIP {fname}")
            print(f"  url: {url}")
            print(f"  reason: {prep.skip_reason} {prep.skip_detail or ''}")
            print()
            continue
        chunks = split_markdown_into_chunks(prep.body_md, max_chunk_size=max_sz, min_chunk_size=min_sz)
        good = [c for c, _ in chunks if chunk_quality_ok(c)]
        preview = (good[0][:200] + "…") if good else "(no quality chunks)"
        print(f"OK {fname}")
        print(f"  url: {url}")
        print(f"  body_len: {len(prep.body_md)} chunks_total: {len(chunks)} chunks_quality_ok: {len(good)}")
        print(f"  first_chunk_preview: {preview!r}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
