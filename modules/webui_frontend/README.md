# WebUI Frontend

## Purpose

React/Vite SPA for the ChironAI Web UI. Communicates **only via HTTP** with the webui_backend; no direct calls to RAG, ingestion, or crawler services.

## Initialization

- **Dependencies**: `npm install` (or `pnpm`/`yarn`) in this directory.
- **Environment**: For standalone dev, set `VITE_API_URL` (or proxy in vite.config) to webui_backend (e.g. `http://localhost:5000`). Default relative `/api/webui` assumes same-origin with backend.
- **Run**: From this directory: `npm run dev` for development; `npm run build` for production.

## API

Uses HTTP API of webui_backend, described in `core/contracts/webui_api`. Types can be generated from OpenAPI if available.

## Structure

- `src/features/` — rag, crawler, ingestion, settings, logs
- `src/shared/` — components, hooks, API client
- `src/api/` — typed client (optional, from OpenAPI)
