# ChironAI RAG Service (`CoreModules/RagService`)

Single installable distribution **`chironai-rag-service`** with two top-level packages:

| Package | Role |
|--------|------|
| **`rag_service`** | Hexagonal RAG pipeline: domain, application use cases, Qdrant/Ollama infrastructure, optional Flask API (`rag_service.api.http`), keyword collections SQLite. |
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

## Data

Keyword collections DB defaults to `rag_service/data/rag_keywords.db` (created next to the `rag_service` package).

## Tests

Pipeline tests live under repository [`tests/rag_service/`](../../tests/rag_service/). Pytest `pythonpath` includes `CoreModules/RagService`.
