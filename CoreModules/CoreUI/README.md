# CoreUI

CoreUI is the React/Vite single-page application for the ChironAI browser UI.
It is served by the backend but talks to product behavior only through HTTP.

## Purpose

- Owns browser-rendered tabs, panels, modals, controls, and shared UI primitives.
- Uses the `/api/webui` HTTP API through `src/services/api.js`.
- Does not import Python modules or call RAG, crawler, ingestion, Docker, or extension internals directly.
- Shows extension UI only through supported extension integration payloads.

## Setup

- Run commands from `CoreModules/CoreUI`.
- Install dependencies with `npm ci`.
- Use `npm install` only when intentionally updating `package-lock.json`.
- For standalone dev, set `VITE_API_PROXY_TARGET` to the backend origin when it is not `http://localhost:8080`.

## Commands

- `npm run dev` starts the Vite development server.
- `npm run build` creates the production bundle in `dist/`.
- `npm run build:strict` builds and checks for lockfile drift.
- `npm run test:run` runs the Vitest suite.
- `npm run test:coverage` runs the CoreUI coverage gate.
- `npm run check:lockfile` verifies that build/test commands did not mutate the lockfile.

## Structure

- `src/components/` contains screens, tabs, dialogs, and shared component wrappers.
- `src/services/` contains HTTP clients and API helpers.
- `src/styles/` contains global styles, design tokens, and component CSS.
- `src/hooks/`, `src/utils/`, `src/constants/`, and `src/types/` hold shared frontend support code.
- `src/App.jsx` owns lazy tab loading and chunk retry behavior.

## Design System

- Tokens live in `src/styles/tokens.css`.
- Global system styles are imported from `src/main.jsx`.
- Prefer existing CoreUI primitives and tokenized classes over one-off markup.
- Use `CoreUIPillTabs` for primary tabs outside cards.
- Use `CoreUISubtabs` for contained secondary navigation.

## Testing

- Run `npm run build` after JSX, TS, or CSS changes that affect rendered UI.
- Add or update Vitest coverage for changed components.
- Update `CoreUIShowcaseTab.jsx` when adding or removing reusable UI primitives.
- Keep `/api/webui` route assumptions aligned with `Core/core/contracts/webui_api.py`.

## Dependencies

- Runtime framework: React and Vite.
- Tests: Vitest and Testing Library.
- Icons should use the existing icon set instead of custom SVG where possible.
- The backend contract is owned by the host WebUI API, not by CoreUI internals.
