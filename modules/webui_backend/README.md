# WebUI Backend

## Purpose

Backend for the Web UI: dashboard, settings, logs, model testing. Aggregates data from rag_service, md_ingestion_service, and crawler_service via their HTTP contracts only. Single entrypoint for the React frontend.

## Initialization

- **Dependencies**: `pip install -r requirements.txt`
- **Environment**: `RAG_SERVICE_URL` (default 5001), `MD_INGESTION_SERVICE_URL` (5002), `CRAWLER_SERVICE_URL` (5003). DB for logs/settings can be added in infrastructure.
- **Run**: `PYTHONPATH=. python -c "from webui_backend.api.http import create_app; create_app().run(port=5000)"` (from repo root). Or mount this app and migrate routes from root `api/http/webui_routes.py`.

## API

Exposes REST API for the frontend (contract: `core/contracts/webui_api`). Depends only on HTTP contracts for rag, md_ingestion, crawler.

## Structure

- `webui_backend/domain/` — entities, ports (RagClient, CrawlerClient, MdIngestionClient)
- `webui_backend/application/` — use cases (get_dashboard_stats, etc.)
- `webui_backend/infrastructure/` — HttpRagClient, HttpCrawlerClient, HttpMdIngestionClient
- `webui_backend/api/` — Flask app (http.py)
