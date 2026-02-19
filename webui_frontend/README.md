# WebUI Frontend

React-based Material 3 WebUI for RAG Proxy.

## Development

```bash
npm install
npm run dev
```

This will start the Vite dev server on port 3000 with hot reload. The dev server proxies API requests to the Flask backend on port 8080.

## Build

```bash
npm run build
```

This creates a production build in the `dist/` directory. The Flask server will automatically serve this build when available.

## Structure

- `src/` - React source code
  - `components/` - React components
  - `services/` - API client and services
  - `styles/` - CSS styles
- `dist/` - Production build (generated)
- `index-react.html` - Entry point for Vite dev server

