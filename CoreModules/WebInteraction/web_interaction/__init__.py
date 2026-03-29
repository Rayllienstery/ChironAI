"""Free web interaction helpers (DuckDuckGo snippets, proxy trigger logic)."""

from web_interaction.supplement import build_web_supplement_text, should_fetch_web_supplement
from web_interaction.search import search_snippets

__all__ = [
    "build_web_supplement_text",
    "should_fetch_web_supplement",
    "search_snippets",
]
