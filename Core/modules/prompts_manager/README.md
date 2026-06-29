# prompts_manager

Host-owned RAG system prompt templates for ChironAI.

## Storage layout

| Location | Purpose |
|----------|---------|
| `prompts_manager/bundled/*.md` | Shipped defaults (for example `system_rag_v1.md`) |
| `Core/data/webui/prompts/*.md` | Mutable runtime store (user edits via WebUI/API) |
| `Core/data/webui/prompts/.trash/` | Deleted prompts awaiting restore or purge |

On first access, any legacy root-level `prompts/` directory is copied into
`Core/data/webui/prompts/` once (marker: `Core/data/webui/prompts/.migrated_from_root`).

## Configuration

- Default prompt name: `rag.prompt` in `Core/config/rag.yaml`
- Override: environment variable `RAG_PROMPT`
- Import: `from prompts_manager import get_rag_system_prompt, PROMPTS_DIR, ...`

## API

WebUI routes under `/api/webui/prompts` read and write the **runtime** store only.
Bundled defaults are read-only through listing/loading but cannot be edited or
deleted through the HTTP API.
