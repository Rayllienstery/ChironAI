# Modules

This directory is a migration tail. Host-owned business services currently live
here, but the root-cleanup target is:

```text
Core/modules/
```

Do not create new long-lived runtime packages in top-level `modules/`. New
host-owned services should be planned for `Core/modules/`; reusable standalone
modules should be considered for `CoreModules/` only when they have a clear
module contract and ownership boundary.

| Project | Responsibility | Target |
|---------|----------------|--------|
| [crawler_service](crawler_service/README.md) | Web/docs crawl into ingestion/indexing flows. | `Core/modules/crawler_service` |
| [extensions_backend](extensions_backend/README.md) | Extension registry, repository metadata, install/update/remove, status, blocklist, and marketplace governance. | `Core/modules/extensions_backend` |
| [webui_backend](webui_backend/README.md) | WebUI backend: dashboard, settings, logs, and aggregation over other services. | `Core/modules/webui_backend` |
| `html_md` | HTML/markdown conversion helpers. | `Core/modules/html_md` |
| `md_indexer` | Config-driven markdown cleanup/indexing pipelines. | `Core/modules/md_indexer` |
| `tools` | Host-owned support tooling. | `Core/modules/tools` |

Related CoreModules:

| CoreModule | Responsibility |
|------------|----------------|
| [RagService / rag_service](../CoreModules/RagService/README.md) | RAG pipeline and `chironai_rag` contracts. |
| [MdIngestionService](../CoreModules/MdIngestionService/README.md) | Markdown/document ingestion, filtering, and chunking. |
| [CoreUI](../CoreModules/CoreUI/README.md) | React SPA. Talks to API only over HTTP. |

Communication between host modules and CoreModules should go through
`core/contracts/`, stable Python protocols, or HTTP contracts. No module should
cross-import another module's concrete implementation as a convenience shortcut.

The repository root `pyproject.toml` currently adds this directory and selected
subdirectories to package/tool paths. During the move to `Core/modules/`, keep
public import names stable first, then consider import renames only as a
separate cleanup.
