# WebUI HTTP client ↔ backend routes

## Client entrypoint

All browser calls use [`src/services/api.js`](../src/services/api.js) with base path
`/api/webui` (must match `core.contracts.webui_api.WEBUI_URL_PREFIX`).

Do not add ad-hoc `fetch('/api/webui/...')` in components; extend `api.js` and
export a named function.

## Backend composition

Flask registers a single blueprint from [`api/http/webui_routes.py`](../../../api/http/webui_routes.py)
which calls `register_*_routes` on domain modules:

| Module | Domain |
|--------|--------|
| `webui_chat_routes.py` | `/models`, `/config`, `/chat`, `/dev-console` |
| `webui_rag_routes.py` | RAG settings, pipeline, Qdrant lifecycle, dashboard |
| `webui_model_tester_routes.py` | Model settings, tester chat |
| `webui_llm_proxy_routes.py` | LLM proxy status, API key, builds |
| `webui_crawler_routes.py` | Crawler, indexer tester, MD pipelines |
| `webui_testing_routes.py` | External-docs testing preview |
| `webui_extensions_routes.py` | Extension registry/install |
| `webui_settings_routes.py` | App settings, keyword collections |
| `webui_observability_routes.py` | Logs, proxy traces, notifications |
| `webui_docker_routes.py` | Docker services |
| `webui_performance_routes.py` | Startup / browser timing |
| `webui_prompt_routes.py` | Prompt templates |
| `webui_session_routes.py` | Session id |
| `webui_version_routes.py` | Version |

Shared helpers: `webui_provider_helpers.py` (not routes).

## Verification (2026-05-31)

- `npm run knip` — clean (no unused exports/files reported).
- `npm run build` — production Vite build succeeds.
- Python: `pytest tests/api tests/webui` after route splits.

When adding a route, update **both** the registering module and `api.js`, and
add or extend an API test under `tests/api` or `tests/webui`.
