# LLM Proxy Builds

Builds are the primary way to route IDE and automation traffic through ChironAI. Each build is a persisted record in app settings (`llm_proxy_builds`) that the proxy resolves when a client sends `"model": "<build-id>"`.

## Why builds exist

Without builds, every client would need to embed provider ids, model tags, RAG collection names, and temperature in each request. Builds centralize that configuration:

- **Stable API contract** — clients keep one `model` string per workflow (e.g. `hard-worker`, `fast-draft`).
- **Per-workflow RAG** — attach different Qdrant collections to different builds.
- **Discoverability** — `GET /v1/models` exposes build ids to OpenAI-compatible clients.
- **UI preview** — Model Tester and build wizard share the same source of truth.

## Create or edit a build

Open **LLM Proxy Builds** → **Add build** (or edit an existing row).

### Step 0 — Basic info

| Field | Rules | Notes |
|-------|-------|-------|
| **Build id** | Unique, lowercase, hyphens ok | Becomes the API `model` value. Immutable after create. |
| **Display name** | Optional | Shown in lists; falls back to build id. |
| **Provider** | Required | From extension/provider catalog. |
| **Model** | Required | Provider-specific model id/tag. |
| **RAG collection** | Optional | Overrides global default for this build only. Empty = inherit. |

Use **Preview** on this step to send a minimal chat through the selected provider before continuing.

### Step 1 — Parameters

Tune generation and proxy behaviour:

- **Temperature, top_p, max_tokens** — passed to the provider adapter.
- **Parameter prefabs** — quick presets (balanced, creative, precise); prefabs may set multiple fields at once.
- **System / prompt template** — optional named prompt from **Template Editor** library.
- **Vision model** — fallback tag when the primary model lacks vision but the client sends images.

Document non-default choices in the build display name so teammates know what changed.

### Step 2 — RAG & retrieval

When a collection is set (here or inherited globally):

- **Hybrid sparse** — combine dense vectors with keyword/BM25-style signals (deployment-dependent).
- **Rerank** — second-stage reranking of retrieved chunks when enabled in settings.
- **RAG trigger** — proxy may skip retrieval on small talk; technical queries score higher.

The wizard shows a **pipeline preview** when available — use it to see effective collection and flag sources.

### Step 3 — Advanced / persistence

- **Ephemeral journal** — when enabled, completed requests are **not** written to RAG Fusion Journal (SQLite). Use for high-volume automation; keep off while debugging in **Logs**.
- **Tool / skill hooks** — build-level toggles for agent features (when supported by provider + host).

Review the summary, save, and confirm the build appears in `GET /v1/models`.

## How the proxy resolves a request

1. Client calls `POST /v1/chat/completions` (or `/v1/responses`, `/v1/messages`) with `"model": "<build-id>"`.
2. Proxy loads the build from settings and merges into effective `proxy_settings`.
3. Optional RAG pipeline runs (collection from precedence chain — see **RAG Collections**).
4. Provider adapter calls the backing LLM.
5. Response streams or returns; trace + journal metadata recorded unless ephemeral.

If the build id is unknown, the proxy returns a client error — match ids exactly (case-sensitive).

## RAG collection on builds

Build-level `rag_collection` sits high in the precedence stack:

1. Request body `collection_name` (per call)
2. App setting `rag_collection`
3. **This build’s `rag_collection`**
4. Legacy blob in persisted proxy settings
5. Host default

Leave the build dropdown **empty** to inherit global **RAG Fusion Proxy → Model settings**. Set it when a build should always hit a specific index (e.g. `ios-docs` vs `internal-runbooks`).

## Multi-build strategies

| Pattern | Example build ids | When to use |
|---------|-------------------|-------------|
| Speed vs quality | `fast`, `quality` | Different models for autocomplete vs deep tasks |
| Domain split | `swift-ui`, `backend-api` | Different collections per codebase |
| Tooling | `no-rag`, `full-rag` | A/B debugging retrieval impact |
| Vision | `vision-main` | Primary text model + explicit vision fallback |

## Testing checklist

Before promoting a build to daily driver:

- [ ] Model Tester returns text with expected latency
- [ ] `GET /v1/models` lists the build id
- [ ] External client succeeds with proxy API key
- [ ] With RAG: trace shows `collection_name` and non-empty context for a doc-specific question
- [ ] With tools/images: verify provider limitations (some models reject tools + vision together)
- [ ] **Logs → Journal** shows the request (unless ephemeral is intentional)

## Common mistakes

- **Renaming build id** — not supported; create a new build and migrate clients.
- **Wrong model tag** — provider lists models dynamically; re-select after provider upgrade.
- **Collection typo** — must match Qdrant exactly; empty dropdown means Qdrant unreachable or no collections.
- **Missing API key** — clients get 503/401 before build resolution matters.
- **Expecting RAG on greetings** — trigger logic may skip retrieval; ask a technical question to test.

## Related topics

- **RAG Collections** — precedence and Qdrant setup
- **Proxy Clients & API** — Cursor, OpenCode, curl
- **Providers** — extension-backed LLM endpoints
- **Logs & Debugging** — traces and journal fields
