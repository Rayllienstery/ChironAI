# RAG Service

## Purpose

Handles the full RAG pipeline: retrieval (embed → vector search → rerank), prompt building, and LLM answers. No UI; exposed via HTTP API and optionally CLI.

## Initialization

- **Dependencies**: Install from project root or from this directory (`pip install -e .` or `pip install -r requirements.txt`).
- **Environment**: See root `config/` for `models.yaml`, `rag.yaml`, `retrieval.yaml`. Set `RAG_EMBED_MODEL`, `OLLAMA_HOST`, `QDRANT_*` as needed.
- **Run HTTP server**: From project root (so `config` and `config.rag_prompts` are on path):
  `PYTHONPATH=. python -c "from rag_service.api.http import create_app; app = create_app(); app.run(host='0.0.0.0', port=5001)"`
  Or: `cd modules/rag_service && PYTHONPATH=../.. flask --app rag_service.api.http:create_app run --port 5001`

## API

RAG endpoints are defined by the contract in `core/contracts/rag_api`. Clients (e.g. webui_backend) call this service via HTTP using that contract.

## Structure

- `rag_service/domain/` — entities, services, ports, errors
- `rag_service/application/` — use cases (answer_question, build_context, search_rag)
- `rag_service/infrastructure/` — Qdrant, Ollama adapters
- `rag_service/api/` — HTTP and CLI
