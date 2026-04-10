# ClawCode (ChironAI Core Module)

Agent layer: OpenAI `POST /v1/chat/completions` and Anthropic `POST /v1/messages` on a dedicated port (shared agent + `rag_query`), optional MCP info HTTP, in-memory traces. Clients set `model` to an Ollama tag (`GET /v1/models` lists tags); LLM Proxy uses **build** presets with `backend: claw` and `ollama_model`. Requires `llm_proxy` on `PYTHONPATH` (monorepo adds `CoreModules/LlmProxy` automatically in `http_server`).

Install editable (from repo root):

```bash
pip install -e CoreModules/ClawCode
```

Run standalone (expects `chironai` on `PYTHONPATH` and `CHIRONAI_WEBUI_DIR`):

```bash
set CHIRONAI_WEBUI_DIR=C:\path\to\AI\WebUI
python -m clawcode
```

See [Claw.md](../../Claw.md) at repository root for full documentation.
