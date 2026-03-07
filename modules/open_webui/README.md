# Open WebUI (Docker)

## Purpose

[Open WebUI](https://github.com/open-webui/open-webui) is a self-hosted chat UI that can connect to Ollama (and other backends). This module documents how it fits into the TMRagFetcher setup and how to control it from the main WebUI.

Open WebUI runs as a **separate Docker container**. The TMRagFetcher WebUI header shows its status (Running/Stopped) and provides buttons to open the Open WebUI page, start, and stop the container.

## Container

- **Image**: `open-webui/open-webui:cuda` (or `open-webui/open-webui` for CPU)
- **Typical mapping**: host port `3000` → container port `8080` (e.g. `3000:8080`)
- **Container name**: by default `open-webui` (configurable via env, see below)

## Initialization

### Create and run the container (one-time)

```bash
docker run -d -p 3000:8080 --name open-webui open-webui/open-webui:cuda
```

For CPU-only:

```bash
docker run -d -p 3000:8080 --name open-webui open-webui/open-webui
```

### Environment variables (TMRagFetcher WebUI backend)

When the main WebUI checks or controls Open WebUI, it uses:

| Variable | Default | Description |
|----------|--------|-------------|
| `OPEN_WEBUI_CONTAINER_NAME` | `open-webui` | Docker container name for start/stop |
| `OPEN_WEBUI_URL` | `http://localhost:3000` | URL to open in browser and to check status (health/root) |

Set these if your container has another name or is exposed on a different host/port.

## Integration with TMRagFetcher WebUI

- In the **header** of the main WebUI (next to Ollama and RAG / Qdrant), an **Open WebUI** status pill shows:
  - **Running** / **Stopped**
  - **Start** / **Stop** — starts or stops the Docker container
  - **Link** — opens Open WebUI in a new tab (`OPEN_WEBUI_URL`)
- Status is determined by an HTTP request to `OPEN_WEBUI_URL`; start/stop use `docker start` / `docker stop` on `OPEN_WEBUI_CONTAINER_NAME`.

## API (backend)

The main WebUI backend (Flask) exposes:

- `GET /api/webui/open-webui/status` — returns `{ "running": bool, "url": str }`
- `POST /api/webui/open-webui/start` — `docker start <container>`
- `POST /api/webui/open-webui/stop` — `docker stop <container>`

## Structure

This module is **documentation and integration only**: no separate Python package. Backend routes live in the main WebUI backend (`api/http/webui_routes.py`); frontend status pill and API calls live in `modules/webui_frontend`.
