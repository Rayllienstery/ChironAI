# MD Ingestion Service

Location: **`CoreModules/MdIngestionService/`** (import name remains `md_ingestion_service`). Add `CoreModules/MdIngestionService` to `PYTHONPATH` alongside the repo root (see root [`pyproject.toml`](../../pyproject.toml)).

## Purpose

Ingests and filters markdown/documents: **`prepare_markdown_for_indexing`** (meta strip, `indexing.yaml` excludes, optional **md_indexer** pipeline, noise headings), path filtering, chunking policy. Used by WebUI collection indexing and local CLI. Outputs to RAG via HTTP (`RagSinkHttp`).

## Initialization

- **Dependencies**: `pip install -r requirements.txt`. From repo root, add root + `CoreModules/MdIngestionService` to PYTHONPATH (pytest already does via `pyproject.toml`).
- **Environment**: `RAG_SERVICE_URL` (default `http://localhost:5001`) for the sink. Source paths and filter rules via CLI/API.
- **Run CLI**: From project root: `python -m md_ingestion_service.api.cli <source_path> [--source-id ID] [--collection NAME] [--dry-run]` with the same `pythonpath` as in root `pyproject.toml` (repo root + `CoreModules/MdIngestionService`).

## API

Consumes sources via `SourceStore` (e.g. `FsSourceStore`); produces chunked payloads to `OutputSink` (e.g. `RagSinkHttp`). Contract for ingestion API: `core/contracts/md_ingestion_api`. RAG ingest contract: `core/contracts/rag_api` (rag_service may expose POST /v1/ingest/chunks).

## Structure

- `md_ingestion_service/domain/` — entities, filtering, **indexing_prepare**, normalization/chunking_policy, ports (SourceStore, OutputSink)
- `md_ingestion_service/application/` — use cases (ingest_local_markdown, dry_run_ingest)
- `md_ingestion_service/infrastructure/` — FsSourceStore, RagSinkHttp
- `md_ingestion_service/api/` — CLI
