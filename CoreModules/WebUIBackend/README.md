# WebUIBackend

WebUIBackend is the canonical backend package for the ChironAI Web UI runtime.
It owns backend entrypoints and legacy helpers that are still being migrated out of the host tail.

## Purpose

- Start the Web UI backend process used by `build_and_run.bat`.
- Serve the CoreUI application and `/api/webui` HTTP routes through host composition.
- Provide helper commands for local startup, shutdown, diagnostics, and ingestion compatibility.
- Keep the root `WebUI/` directory as runtime data rather than frontend or backend source.

## Setup

- Install with `pip install -e CoreModules/WebUIBackend` when developing this package directly.
- Normal repository startup uses `build_and_run.bat` from the root.
- The package expects `Core/` and other CoreModules to be importable.
- Runtime data such as logs and collections stays under the root `WebUI/` and `logs/` folders.

## Entrypoints

- `python -m webui_backend.rag_proxy` starts the backend proxy process.
- `python -m webui_backend.kill_listeners_on_config_port` clears known listeners before startup.
- `python -m webui_backend.print_server_url` prints the configured Web UI URL.
- `webui_backend.paths` centralizes path helpers for the backend package.

## Legacy Helpers

- `apple_docs_extract` and related fetcher helpers support Apple documentation ingestion workflows.
- `ingest_markdown_local` remains for local markdown ingestion compatibility.
- These helpers should be extracted or reduced as dedicated services mature.
- New Web UI HTTP API behavior should be added through the host API layer, not by growing this package blindly.

## Testing

- Run backend startup smoke with `build_and_run.bat` after runtime changes.
- Run API route tests when `/api/webui` behavior changes.
- Run oversized-file audit when splitting legacy helpers.
- Prefer targeted tests around path and startup helpers before broad gates.

## Dependencies

- Host composition under `Core/api/http`.
- CoreUI built assets in `CoreModules/CoreUI/dist`.
- RAG, extension, Docker, and settings services through host wiring.
- Local runtime data under `WebUI/` and `logs/`.
