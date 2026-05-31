# ChironAI RAG Service (`CoreModules/RagService`)

Single installable distribution **`chironai-rag-service`** with two top-level packages:

| Package | Role |
|--------|------|
| **`rag_service`** | Hexagonal RAG pipeline: domain, application use cases, Qdrant/Ollama compatibility infrastructure, optional Flask API (`rag_service.api.http`), keyword collections SQLite. |
| **`chironai_rag`** | Thin boundary: `RagConsumer` kinds, app-setting keys, `ConsumerRagBindings`, `RagProjectPolicy` for proxies and WebUI. |

## Install (monorepo)

From the repository root:

```bash
pip install -e CoreModules/RagService
```

Main app entrypoints also add `CoreModules/RagService` to `sys.path` when present.

## Run the standalone RAG HTTP app (optional)

With project root on `PYTHONPATH` so `config` resolves:

```bash
python -c "from rag_service.api.http import create_app; app = create_app(); app.run(host='0.0.0.0', port=5001)"
```

Or from repo root after editable install:

```bash
flask --app rag_service.api.http:create_app run --port 5001
```

## Runtime Health / Start

The standalone module still exposes runtime dependency helpers for `ollama` and
`qdrant`, but app-level Ollama UX is owned by the `ollama-provider` extension
in the main ChironAI app. The canonical extension source is its dedicated
repository; the bundled copy is only a trusted bootstrap/offline mirror.
Qdrant runtime start/stop goes through RagRuntime and DockerManager; extension
services use DockerManager through host capabilities.

```bash
python -m rag_service health
python -m rag_service start-qdrant
python -m rag_service start-deps --services ollama,qdrant
```

Or after install:

```bash
rag-service health
rag-service start-deps --services ollama,qdrant
```

## Data

Keyword collections DB defaults to `rag_service/data/rag_keywords.db` (created next to the `rag_service` package).

## LLM provider boundary

RagService embed/rerank/chat clients are built from
`rag_service.infrastructure.provider_runtime` and require an extension-backed
`LLMRuntime` (registered via `rag_service.infrastructure.runtime_hooks` when the
main app starts). Ollama-specific HTTP/CLI clients are not part of this package;
use the bundled `ollama-provider` extension or another provider extension.

## Qdrant vector modes

Collection search uses `rag_service.infrastructure.qdrant_repository` with
`named_dense` / `hybrid` detection only. See [`docs/QDRANT_VECTOR_MODES.md`](docs/QDRANT_VECTOR_MODES.md).

## Tests

Pipeline tests live under repository [`tests/rag_service/`](../../tests/rag_service/). Pytest `pythonpath` includes `CoreModules/RagService`.
