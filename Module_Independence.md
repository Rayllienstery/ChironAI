# Module Independence: Pluggable Architecture

This document describes the goal of making modules **fully independent from the application core** so they can be enabled or disabled without changing the core.

---

## Current State

- **Core** = `api/` (Flask app, `webui_routes.py`, `rag_routes.py`), `WebUI/app.py`, root-level `config/`, `application/`, `domain/`, `infrastructure/`.
- **Modules** = **CoreModules/RagService** (`rag_service` + `chironai_rag`, pip `chironai-rag-service`), `modules/crawler_service`, `modules/webui_backend`, `modules/webui_frontend`, `modules/md_indexer`, **CoreModules/MdIngestionService** (`md_ingestion_service` package), etc.

**Problems:**

1. **Core imports modules directly**
   - `api/http/webui_routes.py` adds `CoreModules/RagService` to `sys.path` and imports `rag_service.infrastructure.keyword_collections_sqlite`, `application.rag.*`, and `modules.md_indexer`.
   - Core knows every module by name; there is no “optional” or “pluggable” boundary.

2. **Monolithic route registration**
   - All WebUI routes (prompts, config, chat, RAG, crawler, ollama, rag-tests, dashboard, etc.) live in one large `webui_routes.py` that directly implements or delegates to module code. Enabling “only RAG” or “only crawler” would require editing this file.

3. **Cross-module code dependencies**
   - `md_ingestion_service` can optionally import `rag_service.domain.services.chunking` for chunking logic. So one module can depend on another’s implementation, not only on contracts.

4. **No explicit “enabled modules”**
   - There is no config or registry that lists which modules are active. The frontend shows all tabs; the backend exposes all routes.

---

## Target State: Independent, Pluggable Modules

- **Core** does not import any module by name. It only:
  - Depends on **contracts** in `core/contracts/` (RAG, crawler, md_ingestion, webui API shapes).
  - Optionally loads a **module registry** (e.g. from config: `enabled_modules: [rag, crawler, md_ingestion]`).
  - Registers routes or proxies requests based on that registry and on **HTTP** (or another process boundary) to the corresponding services.

- **Each module** is:
  - **Runnable in isolation** (e.g. its own process or CLI), or at least **loadable only when enabled**.
  - **Communicating via contracts**: HTTP/JSON to other services; no direct Python imports from core or from other modules (except shared types in `core/`).
  - **Optionally providing** “route contributions” or “capabilities” that the core discovers (e.g. via config or a small plugin interface), not by hard-coded imports.

- **Frontend** gets a list of **enabled features** from the backend (e.g. `/api/config` or `/api/features`) and only shows tabs/routes for those features.

---

## Principles

| Principle | Meaning |
|-----------|--------|
| **Core depends only on contracts** | Core uses `core/contracts/*` (RAG, crawler, md_ingestion, webui). No `from rag_service ...` or `from modules.md_indexer ...` in core. |
| **Modules are optional** | A single source of truth (e.g. config or env) defines which modules are enabled. Core and UI adapt to that list. |
| **Communication over the wire** | Where possible, core ↔ module and module ↔ module interaction is HTTP (or another IPC) using contract-defined endpoints. |
| **No cross-module implementation imports** | Modules may depend on `core` (contracts, config, shared). They must not import other modules’ implementations; only call their APIs. |
| **Shared logic in core or contracts** | E.g. chunking constants or rules used by both `rag_service` and `md_ingestion_service` should live in `core` (or a small shared package) and be consumed by both via that shared layer, not by md_ingestion importing rag_service. |

---

## Possible Implementation Directions

### 1. Config-driven enabled modules

- Add something like `enabled_modules: [rag, crawler, md_ingestion, rag_tests]` in app config (YAML/env).
- Core (or a thin “orchestrator”) only starts or registers behaviour for those modules. Others are not loaded and not exposed.

### 2. Each module as a separate process (microservices-style)

- `rag_service`, `md_ingestion_service`, `crawler_service` already have (or can have) their own HTTP servers.
- Core becomes a **gateway/orchestrator**: one Flask app that proxies `/api/rag/*` → rag_service, `/api/crawler/*` → crawler_service, etc., only for enabled modules.
- No Python imports of modules in core; only HTTP client calls and contract-defined DTOs.

### 3. Route contributions (plugin-style, same process)

- Each module exposes a function like `register_routes(app)` or returns a Blueprint and a list of URL prefixes.
- Core has a registry: for each enabled module name, it calls the corresponding `register_routes` or mounts the Blueprint. Disabled modules are never imported.

### 4. Frontend feature flags

- Backend exposes e.g. `GET /api/features` or extends `GET /api/config` with `{ "features": { "rag": true, "crawler": true, "rag_tests": false } }`.
- Frontend shows only tabs/entry points for features that are `true`. Same idea can drive which backend routes are registered (only for enabled features).

### 5. Shared logic in core

- Move chunking constants and shared rules (e.g. from `rag_service.domain.services.chunking`) into `core` (e.g. `core/shared/chunking.py` or under contracts). Then:
  - `rag_service` and `md_ingestion_service` both depend only on `core` for that logic.
  - Removes the need for `md_ingestion_service` to import `rag_service`.

---

## Module-provided UI and communication with the main app

For modules to be truly pluggable, each module must **provide its own UI** and that UI must **communicate with the main project** in a defined way. Below are patterns that fit the current stack (single React SPA + single Flask backend).

### Who provides the UI

- **Today**: All tab components (DashboardTab, RagTab, CrawlerTab, etc.) live in one frontend repo (`webui_frontend`) and are imported directly in `App.jsx`. The “main project” is the shell (App, Tabs, header) plus the backend that serves `/api/webui/*`.
- **Target**: A module either:
  - **Contributes a tab** (id, label, and a way to load the component), or
  - **Contributes a micro-frontend** (e.g. a separate bundle or app loaded in an iframe / at runtime).

The main app should **not** hard-code imports of module components; it should **discover** them from config or from the backend.

### How the main app discovers and shows module UI

1. **Backend exposes “enabled features” and UI descriptors**
   - e.g. `GET /api/config` or `GET /api/features` returns:
     - `features: { rag: true, crawler: true, rag_tests: false }`, and optionally
     - `tabs: [ { id: "rag", label: "RAG / Qdrant", component: "rag" }, { id: "crawler", label: "Crawler / Indexer", component: "crawler" }, ... ]`
   - Only enabled modules appear in `tabs`; the list is driven by the same `enabled_modules` config used on the backend.

2. **Shell renders only tabs for enabled modules**
   - The shell (App.jsx) builds the tab bar from the `tabs` list returned by the API instead of a hard-coded array.
   - For each tab, it needs a **component** to render. Two options:
     - **Same codebase, lazy load**: The shell has a registry mapping `component: "crawler"` → `React.lazy(() => import('./components/CrawlerTab'))`. The module’s UI code can still live in the same repo but in a folder per module (e.g. `modules/crawler_ui/` or `modules/webui_frontend/src/modules/crawler/`). Build can exclude disabled modules to keep the bundle smaller.
     - **Micro-frontend**: `component` points to a URL (e.g. `"/module-crawler/remoteEntry.js"` with Module Federation, or a full URL to a separate app). The shell loads that bundle or embeds an iframe and communicates via a contract (see below).

3. **Contract between shell and module tab**
   - The shell can pass **common props** into every tab component: e.g. `apiBase`, `sessionId`, `theme`, or a shared `api` object. The module tab uses only these and the contract-defined endpoints; it does not assume a specific backend structure beyond the API base URL and the list of endpoints it needs (e.g. `/api/webui/crawler/sources`).
   - If the module UI is in an iframe, the contract is typically **postMessage** (e.g. shell sends `{ type: 'INIT', apiBase, sessionId }`; module sends `{ type: 'NAVIGATE', tab: 'settings' }` to ask the shell to switch tab).

### How the module UI talks to the main project (backend)

- **Single API base**: All UI (shell and module tabs) calls the **same origin** and the same base path, e.g. `/api/webui/...`. The main backend (core) is the single entry point:
  - For **enabled** modules, core either:
    - **Proxies** requests to the module’s service (e.g. `GET /api/webui/crawler/sources` → HTTP forward to crawler_service), or
    - **Registers routes** contributed by the module (e.g. Blueprint under `/api/webui/crawler`) when the module is loaded.
  - For **disabled** modules, those routes are not registered (or return 404); the frontend does not show the tab, so no client calls them.
- **Contract**: The module UI only relies on the **contract** (e.g. `core/contracts/crawler_api.py`): list of endpoints, request/response shapes. It does not care whether the handler lives in the core process or in a separate service behind a proxy.
- **Session and auth**: If the main app uses sessions or auth, the module’s requests are made to the same domain, so cookies/session are shared. No extra auth in the module UI unless the module adds its own.

### Summary: data flow

| Actor | Role |
|-------|------|
| **Config** | Defines `enabled_modules` (e.g. `[rag, crawler]`). |
| **Backend (core)** | Reads config; registers or proxies only enabled modules; exposes `GET /api/features` (and optionally `tabs`) so the frontend knows what to show. |
| **Frontend shell** | Fetches `/api/features` (or `/api/config`); builds tab list; renders tab content by lazy-loading a component or loading a micro-frontend; passes `apiBase` / `sessionId` / theme to each tab. |
| **Module UI** | Renders its tab; calls only the main API base (e.g. `fetch(\`${apiBase}/crawler/sources\`)`); relies on contract-defined endpoints; no direct knowledge of other modules. |

This way the module **provides** its UI (as a tab or micro-frontend) and **communicates** with the main project only through the shared API and the contract; the main project stays in charge of which modules are enabled and how their routes are exposed.

---

## Suggested Order of Work

1. **Introduce “enabled modules” in config** and a single place in core that reads it. No behaviour change yet; just the list and a helper like `is_module_enabled("rag")`.
2. **Backend**: Expose `GET /api/features` (or extend `/api/config`) with `features` and optionally `tabs` (id, label, component key) for enabled modules only.
3. **Frontend shell**: Build the tab list from the API instead of a hard-coded array; optionally lazy-load tab components by component key so disabled modules are not in the bundle. Pass a common contract (e.g. `apiBase`, `sessionId`) into each tab.
4. **Core**: Replace direct imports of a first module (e.g. RAG) with HTTP client calls to that module’s API (if it runs as a separate service) or with a single “RAG adapter” that is only imported when `rag` is enabled. Repeat for other modules.
5. **Move shared chunking (and similar) into core** so that no module imports another module’s implementation.
6. **Optionally** split `webui_routes.py` into per-feature Blueprints that are registered only when the corresponding module is enabled.

---

## References

- Module overview: `modules/README.md`
- Contracts: `core/contracts/` (`rag_api.py`, `crawler_api.py`, `md_ingestion_api.py`, `webui_api.py`)
- Core: `core/README.md`
- Current WebUI routes and module imports: `api/http/webui_routes.py`
- RAG routes: `api/http/rag_routes.py`
- Cross-module chunking dependency: `CoreModules/MdIngestionService/md_ingestion_service/domain/services/chunking_policy.py` (imports `rag_service.domain.services.chunking` or fallback)
