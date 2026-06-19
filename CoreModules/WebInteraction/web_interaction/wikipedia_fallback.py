"""Optional Wikipedia summary when DDG returned no snippets (env-gated)."""

from __future__ import annotations

import json
import os
from typing import Any
from urllib.parse import quote

USER_AGENT = "ChironAI-WebInteraction/1.0 (local RAG proxy; Wikipedia lookup)"


def wikipedia_env_enabled() -> bool:
    raw = os.environ.get("WEB_INTERACTION_WIKIPEDIA")
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def wikipedia_question_eligible(user_message: str, trigger: str) -> bool:
    if trigger != "keywords":
        return False
    t = user_message or ""
    if "```" in t:
        return False
    if len(t) > 280:
        return False
    return not t.count("\n") > 3


def fetch_wikipedia_supplement(user_message: str) -> str:
    """
    OpenSearch + REST summary. Returns formatted block or "".
    """
    if not wikipedia_env_enabled():
        return ""
    q = " ".join((user_message or "").split()).strip()[:120]
    if len(q) < 3:
        return ""
    try:
        import requests
    except ImportError:
        return ""

    params: dict[str, Any] = {
        "action": "opensearch",
        "search": q,
        "limit": 1,
        "namespace": 0,
        "format": "json",
    }
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/api.php",
            params=params,
            timeout=6.0,
            headers={"User-Agent": USER_AGENT},
        )
        r.raise_for_status()
        data = r.json()
    except (requests.RequestException, json.JSONDecodeError, ValueError, TypeError):
        return ""

    if not isinstance(data, list) or len(data) < 4:
        return ""
    titles = data[1]
    urls = data[3]
    if not titles or not urls:
        return ""
    title = titles[0]
    page_url = urls[0]
    safe_title = quote(str(title).replace(" ", "_"), safe="")
    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{safe_title}"
    try:
        r2 = requests.get(summary_url, timeout=6.0, headers={"User-Agent": USER_AGENT})
        r2.raise_for_status()
        sj = r2.json()
    except Exception:
        return ""

    extract = (sj.get("extract") or "").strip() if isinstance(sj, dict) else ""
    if not extract:
        return ""
    extract = extract[:900]
    return (
        "Additional context from Wikipedia (web; verify; RAG primary for APIs and code):\n"
        f"URL: {page_url}\n{extract}\n"
    )
