# Crawler Service

## Purpose

Crawls web/docs sources and sends raw or structured content to md_ingestion_service via HTTP. No direct RAG or UI logic.

## Initialization

- **Dependencies**: `pip install -r requirements.txt`. Playwright when fully implemented.
- **Environment**: `MD_INGESTION_SERVICE_URL` (default `http://localhost:5002`) for pushing results.
- **Run CLI**: From project root: `PYTHONPATH=. python -m crawler_service.api.cli crawl --source-id <id> [--url URL] [--collection NAME]`. (Crawler implementation is stub; migrate from WebUI/app.py to complete.)

## API

Uses `core/contracts/md_ingestion_api` to send crawled content to md_ingestion_service. Exposes API in `core/contracts/crawler_api`.

## Structure

- `crawler_service/domain/` — entities (CrawlSource, CrawlResult, CrawlStatus), ports (CrawlRunner, MdIngestionClient)
- `crawler_service/application/` — use cases (run_crawl_source, run_crawl_all_sources)
- `crawler_service/infrastructure/` — PlaywrightCrawler (stub), MdIngestionHttpAdapter
- `crawler_service/api/` — CLI
