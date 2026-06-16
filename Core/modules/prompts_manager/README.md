# prompts_manager

Host-owned RAG system prompt templates for ChironAI.

## Storage layout

| Location | Purpose |
|----------|---------|
| `prompts_manager/bundled/*.md` | Shipped defaults (for example `system_rag_v1.md`) |
| `WebUI/prompts/*.md` | Mutable runtime store (user edits via WebUI/API) |
| `WebUI/prompts/.trash/` | Deleted prompts awaiting restore or purge |

On first access, any legacy root-level `prompts/` directory is copied into
`WebUI/prompts/` once (marker: `WebUI/prompts/.migrated_from_root`).

## Configuration

- Default prompt name: `rag.prompt` in `Core/config/rag.yaml`
- Override: environment variable `RAG_PROMPT`
- Compatibility import path: `config.rag_prompts` (facade until call sites migrate)

## API

WebUI routes under `/api/webui/prompts` read and write the **runtime** store only.
Bundled defaults are read-only through listing/loading but cannot be edited or
deleted through the HTTP API.
