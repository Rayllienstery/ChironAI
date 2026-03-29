# Web Interaction (`web-interaction`)

Small **CoreModules** package used by the ChironAI LLM Proxy to optionally attach **free** web context (DuckDuckGo text search, optional news, optional page excerpt, optional Wikipedia) to the RAG system prompt.

## What it does not do

- No paid search APIs (Bing, SerpAPI, Tavily, etc.).
- Snippets are **not** a substitute for indexed RAG; they supplement freshness (releases, dates) and low-retrieval framework questions.
- **DuckDuckGo Instant Answer** is not used: the `duckduckgo-search` package exposes `text`, `news`, `images`, etc., not a stable instant-answer API; we rely on `text` (+ optional `news`) only.

## Pipeline (high level)

1. **Query build** — strip code fences, shorten text; for framework triggers add `site:developer.apple.com`; for version-ish keyword triggers optionally add `release`.
2. **Search** — one or two DDG `text` queries, merged and deduped by URL; optional **`news`** hits (past month) when `WEB_INTERACTION_DDG_NEWS=1` and trigger is `keywords`.
3. **Rank** — prefer `developer.apple.com`, `swift.org`, `github.com`, …; soft blocklist for noisy domains; trim to `max_n`.
4. **Cache** — in-process TTL on ranked snippets (`WEB_INTERACTION_CACHE_TTL_S`, default 180s; set `0` to disable).
5. **Optional excerpt** — one HTTP GET for the top result if `WEB_INTERACTION_FETCH_PAGE=1` and URL host is `developer.apple.com` or `swift.org` (strict allowlist).
6. **Optional Wikipedia** — if DDG returned no snippets, trigger is `keywords`, and `WEB_INTERACTION_WIKIPEDIA=1`, try English Wikipedia OpenSearch + REST summary (short question heuristics).

## Install

From the repository root:

```bash
pip install -e CoreModules/WebInteraction
```

The main `chironai` project declares `duckduckgo-search` and related deps; this package also lists `requests` and `html2text` for fetch/Wikipedia.

## Environment

| Variable | Default | Meaning |
|----------|---------|---------|
| `WEB_INTERACTION_ENABLED` | on | `0` / `false` disables all web supplement fetches. |
| `WEB_INTERACTION_MAX_RESULTS` | `3` | Clamped to 1–5 final snippets after ranking. |
| `WEB_INTERACTION_CACHE_TTL_S` | `180` | In-process cache TTL for ranked snippets; `0` disables cache. |
| `WEB_INTERACTION_PREFERRED_DOMAINS` | built-in list | Optional comma-separated substrings to boost in ranking (e.g. `swift.org,github.com`). |
| `WEB_INTERACTION_DDG_REGION` | (auto) | Force DDG region (e.g. `us-en`). If unset and the user message contains Cyrillic, defaults to `ru-ru` for text/news. |
| `WEB_INTERACTION_DDG_NEWS` | off | `1` merges DDG **news** (past month) into the pool for `keywords` triggers only; API may change. |
| `WEB_INTERACTION_FETCH_PAGE` | off | `1` enables one HTML→text excerpt for top URL on strict allowlist (`developer.apple.com`, `swift.org`). |
| `WEB_INTERACTION_WIKIPEDIA` | off | `1` enables Wikipedia fallback when DDG returns no snippets (short factual questions, `keywords` trigger). |

## Reliability

DuckDuckGo behavior can change; failures return an empty or partial supplement and are traced by the proxy (`queries`, `cache_hit`, `ddg_news`, `fetch_used`, `wikipedia_used`, `domains_top`, …).
