# Host-Owned Modules

Host-owned business services live under `Core/modules/`. Reusable standalone
modules belong in `CoreModules/` only when they have a clear module contract and
ownership boundary.

| Project | Responsibility |
|---------|----------------|
| [crawler_service](crawler_service/README.md) | Web/docs crawl into ingestion/indexing flows. |
| [extensions_backend](extensions_backend/README.md) | Extension registry, repository metadata, install/update/remove, status, blocklist, and marketplace governance. |
| [external_docs_rag](external_docs_rag/README.md) | On-demand external documentation fetch and RAG indexing helpers. |
| [webui_backend](webui_backend/README.md) | WebUI backend: dashboard, settings, logs, and aggregation over other services. |
| `html_md` | HTML/markdown conversion helpers. |
| `md_indexer` | Config-driven markdown cleanup/indexing pipelines. |
| `tools` | Host-owned support tooling. |
| [prompts_manager](prompts_manager/README.md) | RAG system prompt templates (bundled defaults + `WebUI/prompts/` runtime store). |

Related CoreModules:

| CoreModule | Responsibility |
|------------|----------------|
| [RagService / rag_service](../../CoreModules/RagService/README.md) | RAG pipeline and `chironai_rag` contracts. |
| [MdIngestionService](../../CoreModules/MdIngestionService/README.md) | Markdown/document ingestion, filtering, and chunking. |
| [CoreUI](../../CoreModules/CoreUI/README.md) | React SPA. Talks to API only over HTTP. |

Communication between host modules and CoreModules should go through
`core/contracts/`, stable Python protocols, or HTTP contracts. No module should
cross-import another module's concrete implementation as a convenience shortcut.

The repository root `pyproject.toml` adds `Core/` and selected `Core/modules/*`
paths to package and test discovery. Public import names (`webui_backend`,
`modules.md_indexer`, etc.) stay stable while physical paths live here.
