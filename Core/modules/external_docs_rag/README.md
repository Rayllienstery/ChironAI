# external_docs_rag

Module for fetching external documentation from the web (e.g. GitHub raw), parsing, chunking, embedding, and indexing into Qdrant. Supports multi-collection RAG with per-collection `top_k` and trigger keywords (e.g. TMArchitecture).

## Structure

- **domain/**: Entities (ExternalSource, FetchedDocument, RagSourceConfig, RagContext), ports (FetchClient, ChunkSink, RagSearchPort, EmbeddingPort).
- **application/**: Use cases: `ingest_source_to_collection`, `resolve_rag_sources_for_request`, `build_merged_rag_context`.
- **infrastructure/**: HTTP fetch, HTML→Markdown parsing, Qdrant chunk sink.
- **config/sources.yaml**: External source definitions (base_url + paths) and RAG source config (collection, top_k, trigger_keywords).

## Usage

- Ingest: run use case `ingest_source_to_collection` for a given ExternalSource (or via CLI/endpoint).
- Multi-RAG and on-demand fetch: when the request contains a trigger keyword (e.g. "TMArchitecture", "TCA", "Alamofire") or `rag_sources` in body, the proxy fetches docs from the web for sources with `on_demand_fetch: true` and merges with RAG (e.g. webcrawl) into the system prompt.
- **Generic discovery**: for any question, CamelCase words (e.g. Kingfisher, SnapKit, RxSwift) are treated as possible framework names. If not already covered by config, the module searches GitHub (search/repositories, language:Swift), fetches the repo's README, and adds it to the context. So unknown frameworks get docs automatically without adding them to config.

## Adding a new framework

1. In **config/sources.yaml**, add an entry under `external_sources`:
   - `id`: unique id (e.g. `snapkit`)
   - `base_url`: GitHub raw base (e.g. `https://raw.githubusercontent.com/SnapKit/SnapKit/main`)
   - `paths`: list of paths to fetch (e.g. `README.md`, `Documentation/Installation.md`)
   - `collection_name`: name for the collection if you later ingest to RAG
2. Add a matching entry under `rag_sources`:
   - `collection_name`: same as above
   - `trigger_keywords`: words that trigger this source (e.g. `["SnapKit", "snapkit"]`)
   - `label`: short label for context (e.g. `SnapKit`)
   - `on_demand_fetch: true`
   - `external_source_id`: same as `id` in external_sources
3. Restart the proxy (or reload config if supported). Queries containing any trigger keyword will fetch that framework's docs from the web and include them in the context.
