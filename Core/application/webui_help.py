"""Load in-app help articles from bundled Markdown under Core/data/webui/help."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.webui_data_paths import default_webui_data_dir

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def bundled_help_dir(repo_root: Path) -> Path:
    """Return the shipped help content directory (not user-overridden runtime data)."""
    return default_webui_data_dir(repo_root) / "help"


def _validate_slug(slug: str) -> str | None:
    value = str(slug or "").strip().lower()
    if not value or not _SLUG_RE.fullmatch(value):
        return None
    return value


def load_help_index(help_root: Path) -> list[dict[str, Any]]:
    """Return article index entries from index.json."""
    index_path = help_root / "index.json"
    if not index_path.is_file():
        return []
    try:
        payload = json.loads(index_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    articles = payload.get("articles") if isinstance(payload, dict) else payload
    if not isinstance(articles, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in articles:
        if not isinstance(item, dict):
            continue
        slug = _validate_slug(str(item.get("slug") or item.get("id") or ""))
        if not slug:
            continue
        rows.append(
            {
                "id": slug,
                "slug": slug,
                "title": str(item.get("title") or slug).strip(),
                "tags": [str(tag).strip() for tag in (item.get("tags") or []) if str(tag).strip()],
                "file": str(item.get("file") or f"{slug}.md").strip(),
            }
        )
    return rows


def _article_file_for_slug(help_root: Path, slug: str, index: list[dict[str, Any]]) -> Path | None:
    entry = next((row for row in index if row.get("slug") == slug), None)
    filename = str((entry or {}).get("file") or f"{slug}.md").strip()
    if not filename or "/" in filename or "\\" in filename or ".." in filename:
        return None
    path = (help_root / filename).resolve()
    try:
        path.relative_to(help_root.resolve())
    except ValueError:
        return None
    return path if path.is_file() else None


def load_help_article(help_root: Path, slug: str) -> dict[str, Any] | None:
    """Load one help article body by slug."""
    normalized = _validate_slug(slug)
    if not normalized:
        return None
    index = load_help_index(help_root)
    entry = next((row for row in index if row.get("slug") == normalized), None)
    if entry is None:
        return None
    path = _article_file_for_slug(help_root, normalized, index)
    if path is None:
        return None
    try:
        content = path.read_text(encoding="utf-8")
    except OSError:
        return None
    return {
        "id": normalized,
        "slug": normalized,
        "title": entry.get("title") or normalized,
        "tags": list(entry.get("tags") or []),
        "content": content,
    }


def search_help(help_root: Path, query: str, *, limit: int = 20) -> list[dict[str, Any]]:
    """Search help titles, tags, and markdown bodies."""
    needle = str(query or "").strip().lower()
    if not needle:
        return []
    index = load_help_index(help_root)
    results: list[dict[str, Any]] = []
    for entry in index:
        slug = str(entry.get("slug") or "")
        article = load_help_article(help_root, slug)
        if article is None:
            continue
        haystacks = [
            str(article.get("title") or "").lower(),
            " ".join(str(tag).lower() for tag in (article.get("tags") or [])),
            str(article.get("content") or "").lower(),
        ]
        if not any(needle in chunk for chunk in haystacks):
            continue
        snippet = _build_snippet(str(article.get("content") or ""), needle)
        results.append(
            {
                "slug": slug,
                "title": article.get("title") or slug,
                "tags": list(article.get("tags") or []),
                "snippet": snippet,
            }
        )
        if len(results) >= max(1, int(limit or 20)):
            break
    return results


def _build_snippet(content: str, needle: str, *, radius: int = 80) -> str:
    lower = content.lower()
    idx = lower.find(needle)
    if idx < 0:
        first_line = next((line.strip() for line in content.splitlines() if line.strip()), "")
        return first_line[:160]
    start = max(0, idx - radius)
    end = min(len(content), idx + len(needle) + radius)
    snippet = content[start:end].replace("\n", " ").strip()
    if start > 0:
        snippet = f"…{snippet}"
    if end < len(content):
        snippet = f"{snippet}…"
    return snippet


__all__ = [
    "bundled_help_dir",
    "load_help_article",
    "load_help_index",
    "search_help",
]
