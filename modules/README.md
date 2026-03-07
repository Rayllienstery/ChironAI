# Modules

Business-domain projects (services and applications) live here. Each subdirectory is a **separate project** with its own README, dependencies, and entrypoints.

| Project | Responsibility |
|---------|----------------|
| [rag_service](rag_service/README.md) | RAG pipeline: retrieval, rerank, prompt building, LLM answers |
| [md_ingestion_service](md_ingestion_service/README.md) | Markdown/document ingestion, filtering, normalization, chunking |
| [crawler_service](crawler_service/README.md) | Web/docs crawling, scheduling, feeding results to md_ingestion |
| [webui_backend](webui_backend/README.md) | WebUI backend: dashboard, settings, logs, aggregation over other services |
| [webui_frontend](webui_frontend/README.md) | React SPA; talks to webui_backend only via HTTP |
| [open_webui](open_webui/README.md) | Open WebUI Docker container; status/start/stop in WebUI header |

Communication between modules is via **interfaces** defined in `core/contracts/`. No cross-import of concrete implementations.
