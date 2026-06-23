# Environment variable reference

Quick index of process env overrides. For precedence vs YAML, app settings, and
LLM Proxy builds, see [`CONFIG_AUTHORITY.md`](CONFIG_AUTHORITY.md).

## Server and logging

| Variable | Affects | Default source |
|----------|---------|----------------|
| `SERVER_PORT` | Main Flask/WebUI backend port | `server.yaml` → `server.port` |
| `CHIRONAI_ACTIVE_SERVER_PORT` | Port this process advertises while running | Same as resolved `SERVER_PORT` |
| `SERVER_HOST` | Bind address | `server.yaml` → `server.host` |
| `WEBUI_PORT` | Legacy standalone WebUI port helper | `server.yaml` → `webui.port` |
| `LOG_LEVEL` | Python logging level name | `server.yaml` → `logging.level` |

## Qdrant

| Variable | Affects | Default source |
|----------|---------|----------------|
| `QDRANT_URL` | HTTP API base URL | `server.yaml` → `qdrant.url` |
| `QDRANT_COLLECTION_NAME` | Default collection name | `server.yaml` → `qdrant.collection_name` |

## Ollama endpoints and models

| Variable | Affects | Default source |
|----------|---------|----------------|
| `OLLAMA_BASE_URL` | Provider-owned Ollama base URL for `ollama-provider` | Derived from chat URL |
| `OLLAMA_CHAT_URL` | Provider-owned Ollama chat URL | `models.yaml` → `ollama.chat_url` |
| `OLLAMA_URL` | Provider-owned Ollama generate URL | `models.yaml` → `ollama.generate_url` |
| `OLLAMA_EMBED_URL` | `/api/embed` URL | `models.yaml` → `ollama.embed_url` |
| `OLLAMA_CHAT_MODEL` | Default chat model tag | `models.yaml` → `ollama.chat_model` |
| `OLLAMA_RERANK_MODEL` | Rerank model tag | `models.yaml` rerank keys |
| `RAG_EMBED_MODEL` | Embed model tag | `models.yaml` → `ollama.embed_model` |
| `OLLAMA_EMBED_TIMEOUT` | Embed HTTP timeout (seconds) | `models.yaml` |

## RAG and retrieval

| Variable | Affects | Default source |
|----------|---------|----------------|
| `RAG_CONTEXT_CHUNK_CHARS` | `get_rag_int("context_chunk_chars")` | `rag.yaml` |
| `RAG_CONTEXT_TOTAL_CHARS` | `get_rag_int("context_total_chars")` | `rag.yaml` |
| `RAG_TOP_K` | `get_retrieval_int("top_k")` | `retrieval.yaml` |
| `RAG_PROMPT` | System prompt stem name | `rag.yaml` → `rag.prompt` |
| `DEFAULT_RAG_TOP_K` | Default top_k when not per-collection | `rag.yaml` |
| `FRAMEWORK_COLLECTION_TTL_DAYS` | Framework collection staleness | `rag.yaml` |

## Extensions and GitHub

| Variable | Affects | Default source |
|----------|---------|----------------|
| `CHIRONAI_EXTENSIONS_REGISTRY_URL` | Remote extension registry | `server.yaml` → `extensions.registry_url` |
| `CHIRONAI_EXTENSIONS_LOCAL_REGISTRY_FALLBACK` | Offline registry path | bundled `extensions/registry/extensions.json` |
| `CHIRONAI_EXTENSIONS_BLOCKLIST_URL` | Emergency blocklist URL | `server.yaml` |
| `CHIRONAI_EXTENSIONS_LOCAL_BLOCKLIST_FALLBACK` | Offline blocklist path | bundled `extensions/registry/blocklist.json` |
| `CHIRONAI_GITHUB_TOKEN` | Authenticated GitHub API | `server.yaml` → `extensions.github_token` |

## LLM Proxy

| Variable | Affects | Default source |
|----------|---------|----------------|
| `LLM_PROXY_V1_INCLUDE_AUTOCOMPLETE_MODEL` | List autocomplete logical model on `/v1/models` | `server.yaml` → `llm_proxy.v1_include_autocomplete_logical_model` |

## Not in root `config` (documented elsewhere)

- Per-build fields on `/v1/chat/completions` override merged `proxy_settings` for one request.
- SQLite `app_settings` keys (`proxy_settings`, `server_port`, `rag_collection`, …) — see `CONFIG_AUTHORITY.md`.
- Extension-owned Docker/Ollama ports — set `OLLAMA_*` when using non-default extension ports.
