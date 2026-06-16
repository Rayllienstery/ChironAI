# WebUI Backend

## Purpose

Canonical backend package for the Web UI. It owns the launch entrypoints used by
`start_webui.bat` and `api.cli`, the modular dashboard/settings/logs target
layers, and the remaining legacy crawl/ingest helpers pending further
extraction.

## Initialization

- **Dependencies**: installed by the root project; standalone work can use `pip install -r requirements.txt`.
- **Environment**: `RAG_SERVICE_URL` (default 5001), `MD_INGESTION_SERVICE_URL` (5002), `CRAWLER_SERVICE_URL` (5003). DB for logs/settings can be added in infrastructure.
- **Run full WebUI**: from the repository root, use `start_webui.bat` or `python -m webui_backend.rag_proxy`.
- **Run modular target app only**: `PYTHONPATH=.;Core;Core/modules/webui_backend python -c "from webui_backend.api.http import create_app; create_app().run(port=5000)"`.

## API

Exposes REST API for the frontend (contract: `core/contracts/webui_api`). The
full runtime entrypoint still registers the route-composition modules under root
`api/http`; target-layer clients here depend only on HTTP contracts for rag,
md_ingestion, and crawler.

## Structure

- `webui_backend/domain/` - entities, ports (RagClient, CrawlerClient, MdIngestionClient)
- `webui_backend/application/` - use cases (get_dashboard_stats, etc.)
- `webui_backend/infrastructure/` - HttpRagClient, HttpCrawlerClient, HttpMdIngestionClient
- `webui_backend/api/` - Flask app (http.py)
- `webui_backend/app.py`, `rag_proxy.py`, `paths.py` - canonical runtime entrypoints and path helpers
- `webui_backend/apple_docs_*`, `ingest_markdown_common.py` - legacy crawl/ingest helpers kept here until they are extracted to narrower modules
