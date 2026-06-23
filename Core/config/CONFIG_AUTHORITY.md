# Configuration Authority

Single reference for **who wins** when the same knob is set in multiple places.

## Application code (canonical getters)

Use **`get_default_*`** in Core, LlmProxy, extensions, and scripts:

| Getter | Purpose |
|--------|---------|
| `get_default_chat_model()` | Default chat model id |
| `get_default_embed_model()` | Default embedding model id |
| `get_default_rerank_model()` | Default rerank model id |
| `get_default_chat_url()` | Default chat HTTP endpoint |
| `get_default_base_url()` | Default LLM base URL (`scheme://host:port`) |
| `get_default_embed_url()` | Default embed HTTP endpoint |
| `get_default_generate_url()` | Default generate HTTP endpoint |

`get_ollama_*` names remain in the **config layer** (`Core/config/env.py`,
`rag_service/config.py`) for env/YAML key compatibility only. Guardrail:
`tests/application/test_ollama_migration_guardrails.py`.

## Resolution layers (general)

| Priority | Layer | Examples |
|----------|--------|----------|
| 1 (highest) | Process environment | `SERVER_PORT`, `OLLAMA_CHAT_MODEL`, `RAG_TOP_K` |
| 2 | App settings (SQLite) | `server_port`, `proxy_settings`, `rag_collection` |
| 3 | Bundled YAML under `config/` | `rag.yaml`, `models.yaml`, `server.yaml`, … |
| 4 (lowest) | Function default argument | `get_rag_int("top_k", 8)` when key missing everywhere |

**LLM Proxy Builds** (selected build id on `/v1/chat/completions`) can override
RAG limits for that request after layer 1–3 are merged into `proxy_settings`
(`context_chunk_chars`, `context_total_chars`, `rag_top_k`, etc.).

**Passthrough** requests (concrete model tag, no build id) use layers 1–3 and
collection params only; they do not read per-build fields.

When `rag_service.config` is importable (`CoreModules/RagService`), its getters
may short-circuit root `config` — tests pin `_rsc = None` to exercise root
precedence documented here.

## Authority table by family

| Family | Getter / API | Env override(s) | YAML source | App settings | Notes |
|--------|----------------|-----------------|-------------|--------------|-------|
| Server port | `get_server_port_metadata()` | `SERVER_PORT` | `server.yaml` → `server.port` | `server_port`, `server_port_last_active` | Env beats settings beats YAML; invalid saved port ignored. |
| Qdrant URL | `get_qdrant_url()` | `QDRANT_URL` | `server.yaml` → `qdrant.url` | `rag_collection` (collection name, not URL) | |
| Qdrant collection | `get_qdrant_collection_name()` / app setting | `QDRANT_COLLECTION_NAME` | `server.yaml` → `qdrant.collection_name` | `rag_collection` | |
| Default chat model | `get_default_chat_model()` (`get_ollama_chat_model()` in config layer) | `OLLAMA_CHAT_MODEL` | `ollama.chat_model` | — | Empty env string is valid (clears model). |
| Default embed model | `get_default_embed_model()` (`get_ollama_embed_model()` in config layer) | `RAG_EMBED_MODEL` | `embed_model`, then `embed_model_last_resort` | — | Skips empty YAML strings. |
| Default rerank model | `get_default_rerank_model()` (`get_ollama_rerank_model()` in config layer) | `OLLAMA_RERANK_MODEL` | `rerank_model`, then `rerank_model_last_resort` | — | Does **not** read `retrieval.yaml`. |
| Default chat URL | `get_default_chat_url()` (`get_ollama_chat_url()` in config layer) | `OLLAMA_CHAT_URL` | `models.yaml` → `ollama.chat_url` | — | |
| Default LLM base | `get_default_base_url()` (`get_ollama_base_url()` in config layer) | `OLLAMA_BASE_URL` | Derived from chat URL host | — | Strips `/api/*` suffixes from env. |
| Default generate URL | `get_default_generate_url()` (`get_ollama_generate_url()` in config layer) | `OLLAMA_URL` | `ollama.generate_url` | — | |
| Default embed URL | `get_default_embed_url()` (`get_ollama_embed_url()` in config layer) | `OLLAMA_EMBED_URL` | `ollama.embed_url` | — | |
| RAG ints | `get_rag_int(key, default)` | `RAG_CONTEXT_CHUNK_CHARS`, `RAG_CONTEXT_TOTAL_CHARS` (mapped keys only) | `rag.yaml` | Via `proxy_settings` / builds | Other keys: YAML then default. |
| Retrieval ints | `get_retrieval_int(key, default)` | `RAG_TOP_K` when `key == "top_k"` | `retrieval.yaml` | Build `rag_top_k` when merged | |
| RAG prompt name | `get_rag_prompt_name()` | `RAG_PROMPT` | `rag.prompt` | — | |
| Proxy rerank toggle | `get_proxy_rerank_enabled()` | — | `rag.proxy_rerank_enabled` | — | |
| Extensions registry | `get_extensions_registry_url()` | `CHIRONAI_EXTENSIONS_REGISTRY_URL` | `server.extensions.registry_url` | — | |
| Extensions blocklist | `get_extensions_blocklist_url()` | `CHIRONAI_EXTENSIONS_BLOCKLIST_URL` | `server.extensions.blocklist_url` | — | |
| GitHub token | `get_github_token()` | `CHIRONAI_GITHUB_TOKEN` | `extensions.github_token` | — | |

## Per-request overrides (LLM Proxy)

| Field | Build JSON key | Merged into |
|-------|----------------|-------------|
| Context limits | `context_chunk_chars`, `context_total_chars` | `proxy_settings` → handler budget |
| Retrieval breadth | `rag_top_k` | `proxy_settings` |
| Rerank model | `rerank_model` in proxy settings / build | `apply_selected_rerank_model()` on client |
| Collection | `rag_collection` | trace + retrieval |

## Tests

Precedence is locked by:

- `tests/config/test_config_precedence.py` — env vs YAML for RAG, retrieval, models, Qdrant
- `tests/config/test_server_port.py` — server port metadata order
- `tests/config/test_ollama_base_url.py` — Ollama URL derivation
- `tests/config/test_extensions_config.py` — extensions URLs

## Related docs

- `config/README.md` — file layout and parameter descriptions
- `config/ENV_REFERENCE.md` — flat env var index
- `DEPENDENCIES.md` — runtime services
- `docs/legacy_map.md` — legacy tail ownership and refactor status
