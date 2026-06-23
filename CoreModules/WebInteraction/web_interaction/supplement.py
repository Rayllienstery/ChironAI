"""High-level: should we fetch, and build supplement text."""

from __future__ import annotations

from typing import Any

from web_interaction.cache import cache_get, cache_set, make_cache_key
from web_interaction.config import ddg_news_enabled, max_results_default, web_interaction_globally_enabled
from web_interaction.fetch_excerpt import excerpt_for_top_snippet, fetch_page_env_enabled
from web_interaction.format import format_page_excerpt_block, format_web_supplement
from web_interaction.query_build import build_search_queries
from web_interaction.ranking import rank_and_trim, top_domains
from web_interaction.search import search_multi_with_backend, search_news_snippets
from web_interaction.triggers import WebSupplementTrigger, decide_trigger
from web_interaction.wikipedia_fallback import (
    fetch_wikipedia_supplement,
    wikipedia_env_enabled,
    wikipedia_question_eligible,
)


def should_fetch_web_supplement(
    user_message: str,
    *,
    master_enabled: bool,
    on_keywords: bool,
    on_low_confidence_framework: bool,
    max_score: float,
    confidence_threshold: float,
) -> tuple[bool, str]:
    """
    Returns (should_fetch, trigger) where trigger is none|keywords|low_confidence_framework.
    """
    if not master_enabled or not web_interaction_globally_enabled():
        return False, "none"
    t = decide_trigger(
        user_message,
        on_keywords=on_keywords,
        on_low_confidence_framework=on_low_confidence_framework,
        max_score=max_score,
        confidence_threshold=confidence_threshold,
    )
    if t == "none":
        return False, "none"
    return True, t


def build_web_supplement_bundle(
    user_message: str,
    *,
    trigger: WebSupplementTrigger,
    max_n: int | None = None,
    search_backend: Any = None,
    region: str | None = None,
    ddg_news: bool | None = None,
    fetch_page: bool | None = None,
    wikipedia: bool | None = None,
) -> tuple[str, dict[str, Any]]:
    """
    Search, rank, cache, format. Returns (markdown block or "", debug meta for trace).
    """
    meta: dict[str, Any] = {
        "queries": [],
        "cache_hit": False,
        "fetch_used": False,
        "wikipedia_used": False,
        "ddg_news": False,
        "domains_top": [],
        "snippets_count": 0,
        "snippets_chars": 0,
    }
    use_news = ddg_news_enabled() if ddg_news is None else bool(ddg_news)
    use_fetch = fetch_page_env_enabled() if fetch_page is None else bool(fetch_page)
    use_wiki = wikipedia_env_enabled() if wikipedia is None else bool(wikipedia)

    queries = build_search_queries(user_message, trigger)
    meta["queries"] = list(queries)
    if not queries:
        return "", meta

    n = max_n if max_n is not None else max_results_default()
    reg = region or ""

    key = make_cache_key(
        list(queries),
        trigger,
        n,
        reg,
        variant="news1" if use_news else "news0",
    )
    cached = cache_get(key)
    if cached is not None:
        ranked, aux = cached
        meta["cache_hit"] = True
        meta["ddg_news"] = bool(aux.get("ddg_news"))
    else:
        pool = search_multi_with_backend(queries, max(n * 2, 6), search_backend, region=region or None)
        if trigger == "keywords" and use_news:
            news_hits = search_news_snippets(queries[0], min(3, n), region=region or None)
            if news_hits:
                meta["ddg_news"] = True
            pool.extend(news_hits)
        ranked = rank_and_trim(pool, n)
        cache_set(key, ranked, {"ddg_news": meta["ddg_news"]})

    meta["domains_top"] = top_domains(ranked, 5)
    meta["snippets_count"] = len(ranked)

    text = format_web_supplement(ranked)
    if use_fetch:
        ex_txt, ex_url = excerpt_for_top_snippet(ranked)
        if ex_txt:
            meta["fetch_used"] = True
            text += format_page_excerpt_block(ex_url, ex_txt)

    if not ranked and use_wiki and wikipedia_question_eligible(user_message, trigger):
        wpart = fetch_wikipedia_supplement(user_message)
        if wpart:
            meta["wikipedia_used"] = True
            text = (text + "\n\n" + wpart).strip() if text else wpart

    meta["snippets_chars"] = len(text)
    return text, meta


def build_web_supplement_text(
    user_message: str,
    *,
    trigger: WebSupplementTrigger = "keywords",
    max_n: int | None = None,
    search_backend: Any = None,
    region: str | None = None,
) -> str:
    """
    Build DDG queries from user_message + trigger, search (multi-query merge), format block.
    """
    text, _ = build_web_supplement_bundle(
        user_message,
        trigger=trigger,
        max_n=max_n,
        search_backend=search_backend,
        region=region,
    )
    return text
