"""Format web search results for the system prompt."""

from __future__ import annotations

from datetime import datetime, timezone

from web_interaction.search import Snippet

WEB_BLOCK_INTRO = """Additional context from web search (snippet results; as of request date {iso_date} UTC):
This block is for release dates, versioning, and general freshness only. For APIs, signatures, and code, trust the RAG/documentation snippets above.
Do not merge facts from RAG and web in a single claim. If sources disagree, state both and label them (RAG vs web).

"""


def format_web_supplement(snippets: list[Snippet], *, iso_date: str | None = None) -> str:
    if not snippets:
        return ""
    when = iso_date or datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [WEB_BLOCK_INTRO.format(iso_date=when)]
    for i, s in enumerate(snippets, start=1):
        title = (s.get("title") or "Untitled").strip()
        url = (s.get("url") or "").strip()
        body = (s.get("body") or "").strip()
        line = f"[{i}] {title}"
        if url:
            line += f"\nURL: {url}"
        if body:
            line += f"\n{body}"
        parts.append(line)
    return "\n\n".join(parts) + "\n"


def format_page_excerpt_block(url: str, plain_text: str) -> str:
    """Append after DDG snippets; clearly labeled web page excerpt."""
    t = (plain_text or "").strip()
    if not t:
        return ""
    u = (url or "").strip()
    return (
        "\n---\nExcerpt from page (web; RAG remains primary for APIs and signatures):\n"
        f"URL: {u}\n{t}\n"
    )
