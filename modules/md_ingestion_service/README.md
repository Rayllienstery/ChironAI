# MD Ingestion Service

## Purpose

Ingests and filters markdown/documents: parsing, normalization, filtering rules, chunking policy. Prepares content for indexing; outputs to RAG service via HTTP contract (`RagSinkHttp` calls rag_service when `/v1/ingest/chunks` is available).

## Initialization

- **Dependencies**: `pip install -r requirements.txt`. From repo root, add root to PYTHONPATH if using rag_service chunking.
- **Environment**: `RAG_SERVICE_URL` (default `http://localhost:5001`) for the sink. Source paths and filter rules via CLI/API.
- **Run CLI**: From project root: `PYTHONPATH=. python -m md_ingestion_service.api.cli <source_path> [--source-id ID] [--collection NAME] [--dry-run]`

## API

Consumes sources via `SourceStore` (e.g. `FsSourceStore`); produces chunked payloads to `OutputSink` (e.g. `RagSinkHttp`). Contract for ingestion API: `core/contracts/md_ingestion_api`. RAG ingest contract: `core/contracts/rag_api` (rag_service may expose POST /v1/ingest/chunks).

## Structure

- `md_ingestion_service/domain/` — entities, filtering/normalization/chunking_policy, ports (SourceStore, OutputSink)
- `md_ingestion_service/application/` — use cases (ingest_local_markdown, dry_run_ingest)
- `md_ingestion_service/infrastructure/` — FsSourceStore, RagSinkHttp
- `md_ingestion_service/api/` — CLI
