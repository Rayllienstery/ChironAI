"""
Discover a GitHub repo by name (search API) and fetch README for generic framework docs.
Uses public GitHub API (no auth); 60 requests/hour unauthenticated.
Supports fetching by version (tag) and resolving latest release.
"""

from __future__ import annotations

import re
from typing import Any

try:
    import requests
except ImportError:
    requests = None  # type: ignore

from external_docs_rag.domain.ports import FetchClient
from external_docs_rag.domain.services.chunking import chunk_quality_ok, split_markdown_into_chunks
from external_docs_rag.domain.services.context_ordering import (
    reorder_chunks_for_version_question,
    wants_version_or_requirements,
)
from external_docs_rag.infrastructure.content_parser import parse_document_to_markdown

GITHUB_API_SEARCH = "https://api.github.com/search/repositories"
GITHUB_API_RELEASES_LATEST = "https://api.github.com/repos/{full_name}/releases/latest"
GITHUB_RAW_TEMPLATE = "https://raw.githubusercontent.com/{full_name}/{ref}/README.md"
USER_AGENT = "ExternalDocsRAG/1.0"

# raw.githubusercontent.com/owner/repo/ref/path -> ref is the 4th path segment
RAW_GITHUB_URL_RE = re.compile(
    r"^https?://raw\.githubusercontent\.com/([^/]+)/([^/]+)/([^/]+)(/.*)?$"
)


def get_latest_release_tag(full_name: str) -> str | None:
    """
    Get latest release tag for a repo (e.g. Alamofire/Alamofire -> "5.11.1").
    Returns tag without leading "v". None on error or no releases.
    """
    if not requests:
        return None
    try:
        url = GITHUB_API_RELEASES_LATEST.format(full_name=full_name)
        resp = requests.get(
            url,
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": USER_AGENT},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        tag = (data.get("tag_name") or "").strip()
        if tag.startswith("v"):
            tag = tag[1:]
        return tag if tag else None
    except Exception:
        return None


def replace_ref_in_raw_github_url(base_url: str, new_ref: str) -> str:
    """
    Replace the ref (branch/tag) in a raw.githubusercontent.com URL.
    E.g. .../Alamofire/master -> .../Alamofire/5.11.1
    """
    m = RAW_GITHUB_URL_RE.match(base_url.rstrip("/"))
    if not m:
        return base_url
    owner, repo, _old_ref, rest = m.group(1), m.group(2), m.group(3), m.group(4) or ""
    return f"https://raw.githubusercontent.com/{owner}/{repo}/{new_ref}{rest}"


def parse_raw_github_full_name(base_url: str) -> str | None:
    """Extract owner/repo from raw.githubusercontent.com URL, or None."""
    m = RAW_GITHUB_URL_RE.match(base_url.rstrip("/"))
    if not m:
        return None
    return f"{m.group(1)}/{m.group(2)}"


def discover_repo(name: str) -> tuple[str, str] | None:
    """
    Search GitHub for a repo by name (Swift/iOS oriented). Returns (full_name, default_branch) or None.
    """
    if not requests:
        return None
    try:
        resp = requests.get(
            GITHUB_API_SEARCH,
            params={"q": f"{name} language:Swift", "sort": "stars", "per_page": 1},
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": USER_AGENT},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        items = data.get("items") or []
        if not items:
            return None
        repo = items[0]
        full_name = repo.get("full_name")
        default_branch = repo.get("default_branch") or "main"
        if not full_name:
            return None
        return (full_name, default_branch)
    except Exception:
        return None


def discover_and_fetch_readme(
    name: str,
    fetch_client: FetchClient,
    context_max_chars: int,
    question: str | None = None,
    version_ref: str | None = None,
) -> tuple[str, list[dict[str, Any]]] | None:
    """
    Discover a GitHub repo by name, fetch README.md raw, parse and chunk.
    When question asks for version/requirements, those sections are prioritized.
    If version_ref is set, fetch from that tag; else if question asks for version/requirements,
    resolve latest release tag and fetch from it, and prepend "Latest release version: X.Y.Z" to context.
    Returns (context_text, chunks_info) or None on failure.
    """
    result = discover_repo(name)
    if not result:
        return None
    full_name, branch = result
    ref = version_ref
    resolved_latest: str | None = None
    if ref is None and question and wants_version_or_requirements(question):
        resolved_latest = get_latest_release_tag(full_name)
        if resolved_latest:
            ref = resolved_latest
    if ref is None:
        ref = branch
    raw_url = GITHUB_RAW_TEMPLATE.format(full_name=full_name, ref=ref)
    doc = fetch_client.fetch(raw_url)
    if doc is None:
        return None
    md = parse_document_to_markdown(doc)
    if not md or len(md.strip()) < 100:
        return None
    parts: list[str] = []
    chunks_info: list[dict[str, Any]] = []
    total = 0
    if resolved_latest:
        parts.append(f"Latest release version: {resolved_latest}")
        total += len(parts[0]) + 2
    raw_chunks = split_markdown_into_chunks(md)
    if question and wants_version_or_requirements(question):
        raw_chunks = reorder_chunks_for_version_question(raw_chunks)
    for chunk_text, section_path in raw_chunks:
        if total >= context_max_chars:
            break
        if not chunk_quality_ok(chunk_text):
            continue
        remaining = context_max_chars - total
        take = chunk_text[:remaining].rstrip() if len(chunk_text) > remaining else chunk_text
        if not take:
            continue
        parts.append(take)
        total += len(take) + 2
        chunks_info.append({
            "source": name,
            "url": raw_url,
            "path": "README.md",
            "label": name,
        })
    context_text = "\n\n".join(parts)
    return (context_text, chunks_info) if context_text else None


__all__ = [
    "discover_repo",
    "discover_and_fetch_readme",
    "get_latest_release_tag",
    "parse_raw_github_full_name",
    "replace_ref_in_raw_github_url",
]
