# Getting Started

ChironAI is a local, model-agnostic **RAG platform**: it retrieves relevant document chunks from Qdrant, assembles a prompt, and forwards the request to your configured LLM provider (Ollama, extension-backed cloud APIs, etc.). The WebUI (CoreUI) is the control surface; external tools talk to the **RAG Fusion Proxy** over OpenAI-compatible HTTP.

This guide gets you from a cold start to a working chat with optional RAG in under 15 minutes.

## What you need

| Component | Purpose | Where to check |
|-----------|---------|----------------|
| WebUI server | Hosts CoreUI + `/api/webui` + `/v1/*` proxy | **Dashboard** service cards |
| LLM provider | Generates answers (Ollama, extension provider, …) | **Dependencies**, **Extensions** |
| Qdrant (optional) | Vector store for RAG collections | **RAG / Qdrant**, **Docker** |
| Indexed content (optional) | Chunks inside a collection | **Crawler**, **RAG** tab |

You can run without RAG (plain proxy). RAG requires Qdrant plus at least one populated collection.

## 1. Start the stack

1. Run `start_webui.bat` (Windows) or your deployment launch script.
2. Open the WebUI URL shown in the terminal (default port is in **Settings → Server port**).
3. On **Dashboard**, confirm:
   - WebUI is healthy
   - Your LLM provider extension or Ollama endpoint is reachable
   - Qdrant shows **running** if you plan to use RAG

If startup fails, open `logs/webui_errors.log` on disk or the **Logs** tab.

## 2. Generate a proxy API key

All `/v1/*` routes are **fail-closed** without a key.

1. Open **RAG Fusion Proxy** → **Overview** → **Security**.
2. Click **Generate key** (first time) or **Reveal key** to copy.
3. Store the key in your IDE or client as `Authorization: Bearer <key>` or header `x-api-key: <key>`.

Without a key, clients receive `503 server_configuration_error`. With a wrong key, `401 authentication_error`.

## 3. Create your first LLM Proxy build

A **build** is a named profile. Clients set `"model": "<build-id>"` in API requests; the proxy resolves provider, model, RAG collection, and parameters.

1. Open **LLM Proxy Builds** in the sidebar.
2. Click **Add build** and complete the wizard:
   - **Build id** — stable API name (e.g. `dev-main`). Lowercase, hyphens allowed. Cannot change after save.
   - **Display name** — label in the UI only.
   - **Provider + Model** — the LLM that generates text.
   - **RAG collection** (optional) — Qdrant collection for this build only.
3. Save and note the build id.

See **LLM Proxy Builds** help for wizard steps (parameters, hybrid retrieval, rerank, prompts).

## 4. Smoke-test in the WebUI

Before wiring Cursor or OpenCode:

1. **RAG Fusion Proxy** → **Model Tester** — pick your build, send a short prompt, inspect latency and response.
2. If RAG is enabled, expand trace metadata and confirm `collection_name` and retrieval steps.
3. **Logs** → **RAG Fusion Journal** — verify the request was persisted (unless ephemeral mode is on for that build).

## 5. Point an external client

Minimal OpenAI-compatible example (replace host, port, key, build id):

```bash
curl -s http://127.0.0.1:8080/v1/chat/completions \
  -H "Authorization: Bearer YOUR_PROXY_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "dev-main",
    "messages": [{"role": "user", "content": "Hello"}]
  }'
```

Supported entry points include:

- `POST /v1/chat/completions` — OpenAI chat (Cursor, Kilo, many SDKs)
- `POST /v1/responses` — OpenAI Responses API (OpenCode)
- `POST /v1/messages` — Anthropic Messages (send header `anthropic-version: 2023-06-01`)

`GET /v1/models` lists build ids (and optional logical models such as autocomplete).

See **Proxy Clients & API** for IDE-specific setup.

## 6. Enable RAG (when Qdrant is ready)

1. **Crawler / Indexer** — follow [Indexing Content](indexing) from **Add Source** through **Create Collection** (see `#sources`, `#crawl-actions`, `#create-collection`).
2. **RAG / Qdrant** — confirm the collection appears and run a retrieval test.
3. Attach the collection on the build **or** set defaults under **RAG Fusion Proxy → Model settings**.
4. Re-test in **Model Tester** with a question that should hit your docs.

Collection precedence is documented in **RAG Collections**.

## CoreUI map (first week)

| Sidebar tab | Use it for |
|-------------|------------|
| **Dashboard** | Health overview, quick links |
| **LLM Proxy Builds** | Build CRUD, per-build RAG |
| **RAG Fusion Proxy** | Global proxy/RAG defaults, Model Tester, API key |
| **RAG / Qdrant** | Collections, retrieval tests |
| **Crawler / Indexer** | Ingestion jobs |
| **Logs** | Live traces + persisted journal |
| **Extensions** | Providers, Docker services |
| **Settings** | Theme, locale, port, developer mode |
| **Help** | This knowledge base (`?help=<slug>` deep links) |

## Recommended learning path

1. Plain proxy (build + Model Tester + one client)
2. Index a small doc set → one collection
3. Attach collection to build → verify traces
4. Tune RAG Fusion global settings (hybrid, rerank, trigger threshold)
5. Read **Logs & Debugging** when results look wrong

## Glossary

- **CoreUI** — React frontend you are using now.
- **Build** — Named proxy profile referenced as `model` in `/v1` API calls.
- **RAG Fusion Proxy** — Product name for the `/v1` HTTP surface with retrieval orchestration.
- **Collection** — Qdrant index of embedded document chunks.
- **Journal** — SQLite history of completed proxy requests (`Logs` tab).
