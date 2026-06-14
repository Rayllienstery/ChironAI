# CoreUI (ChironAI Web UI frontend)

## Purpose

React/Vite SPA for the ChironAI Web UI (served from `CoreModules/CoreUI`). Communicates **only via HTTP** with the webui_backend; no direct calls to RAG, ingestion, or crawler services.

## Initialization

- **Dependencies**: `npm ci` in this directory. Use `npm install` only when intentionally updating `package-lock.json`.
- **Environment**: For standalone dev, set `VITE_API_PROXY_TARGET` to the running backend origin when it is not on `http://localhost:8080`. Default relative `/api/webui` assumes same-origin with backend.
- **Run**: From this directory: `npm run dev` for development; `npm run build` for production.
- **Lockfile check**: After dependency-neutral builds, run `npm run check:lockfile` or use `npm run build:strict` to build and fail on accidental `package-lock.json` drift.

## API

Uses HTTP API of webui_backend, described in `core/contracts/webui_api`. Types can be generated from OpenAPI if available.

## Structure

- `src/features/` — rag, crawler, ingestion, settings, logs
- `src/shared/` — components, hooks, API client
- `src/api/` — typed client (optional, from OpenAPI)
