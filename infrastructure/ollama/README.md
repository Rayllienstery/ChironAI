# Root `infrastructure/ollama` compatibility boundary

Ollama **provider behavior** belongs in the `ollama-provider` extension
(`extensions/bundled/ollama-provider` is a bootstrap/offline mirror only).
This package keeps **documented compatibility adapters** for:

- LLM Proxy OpenAI/Ollama bridging (`ollama_compat.py`)
- Standalone / fallback HTTP+CLI clients when `LLMRuntime` is unavailable
- Targeted WebUI health checks (`invoke_ping` from RAG routes)

RagService duplicates some adapters under `rag_service.infrastructure.ollama_*`
for standalone installs; see [`CoreModules/RagService/README.md`](../../CoreModules/RagService/README.md).

Migration guide: [`OLLAMA_EXTENSION_MIGRATION_TODO.md`](../../OLLAMA_EXTENSION_MIGRATION_TODO.md).

## Module map

| Module | Role | New code should import? |
|--------|------|-------------------------|
| `cli_runner.py` | Subprocess bridge to `ollama_interactor` CLI | Only from adapters below or allowlisted routes |
| `chat_client.py` | Domain `ChatLLMClient` via CLI | Via `__init__` exports or RagService wiring |
| `embed_client.py` | Domain `EmbeddingProvider` via CLI | Same |
| `rerank_client.py` | Rerank with `/api/rerank` + generate fallback | Same |
| `openai_ollama_tool_bridge.py` | OpenAI messages ↔ Ollama tool wire format | **LlmProxy only** (`ollama_compat`) |
| `openai_multipart_vision.py` | Vision multipart normalization | **LlmProxy only** |
| `model_capabilities.py` | Cached capability flags from `/api/show` | **LlmProxy only** |
| `model_brand.py` | Brand key for UI/icons | **LlmProxy only** |
| `gemini_model_id.py` | Gemini family detection | **LlmProxy only** |
| `ollama_model_visibility.py` | Model list filtering helpers | Legacy proxy/WebUI helpers |

## Import guardrail

`tests/application/test_ollama_migration_guardrails.py` blocks new
`from infrastructure.ollama` imports unless the file is in
`ALLOWED_INFRASTRUCTURE_OLLAMA_IMPORT_FILES`.

Current allowlist (2026-05-31):

- `CoreModules/LlmProxy/llm_proxy/ollama_compat.py`
- `api/http/webui_rag_routes.py` — Qdrant/Ollama status ping only
- `infrastructure/ollama/*` internal imports
- Focused tests under `tests/infrastructure`, `tests/llm_proxy`, `tests/api`

Do **not** add CoreUI or new feature modules to this list; use provider catalog,
`LLMRuntime`, or `api.http.extensions_service_access`.
