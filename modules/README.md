# Modules

Business-domain projects (services and applications) live here. Each subdirectory is a **separate project** with its own README, dependencies, and entrypoints.

| Project | Responsibility |
|---------|----------------|
| [RagService / rag_service](../CoreModules/RagService/README.md) | RAG pipeline + `chironai_rag` contracts (package **CoreModules/RagService**, pip `chironai-rag-service`) |
| [md_ingestion_service](../CoreModules/MdIngestionService/README.md) | Markdown/document ingestion, filtering, `prepare_markdown_for_indexing`, chunking (package under **CoreModules**) |
| [crawler_service](crawler_service/README.md) | Web/docs crawling, scheduling, feeding results to md_ingestion |
| [webui_backend](webui_backend/README.md) | WebUI backend: dashboard, settings, logs, aggregation over other services |
| [CoreUI](../CoreModules/CoreUI/README.md) | React SPA (WebUI); talks to API via HTTP |
| [open_webui](open_webui/README.md) | Open WebUI Docker container; status/start/stop in WebUI header |

Communication between modules is via **interfaces** defined in `core/contracts/`. No cross-import of concrete implementations.

The repository root [`pyproject.toml`](../pyproject.toml) installs the **core** Python packages (`domain`, `application`, `api`, …) as the `chironai` distribution; `modules/*` often stay on `PYTHONPATH` via pytest or manual `sys.path` until each gets its own `pyproject.toml` for a full split.
