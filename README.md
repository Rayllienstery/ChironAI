# ChironAI

ChironAI is a Retrieval-Augmented Generation (RAG) assistant focused on Apple platforms (Swift, iOS, SwiftUI). It uses local LLMs via Ollama, a vector database via Qdrant, and an optional LLM-based reranker to improve retrieval quality.

## What it does
- Crawls and indexes documentation sources into a Qdrant collection.
- Accepts user questions through the WebUI and/or CLI.
- Retrieves relevant chunks from Qdrant, optionally reranks them, and produces a grounded answer.

## Core components
- Qdrant: vector database for embeddings and chunk storage.
- Ollama: local LLM provider (chat, embeddings, reranking).
- RAG prompts: versioned system prompts in prompts/.

## Configuration
- Main RAG settings: config/rag.yaml.
- Prompt selection: set `rag.prompt` in config/rag.yaml or override via RAG_PROMPT.

## Development (Python packaging)

Install the **core library** and dev tools from the repository root (editable installs, same idea as local Swift packages):

```bash
pip install -r requirements-dev.txt
```

This installs `chironai` from [`pyproject.toml`](pyproject.toml) (packages: `application`, `api`, `config`, `core`, `domain`, `infrastructure`, `utils`) plus `ollama-interactor`. Console entry points: `tmrag` / `chironai` → `api.cli`.

- Tests: `pytest` (config in `pyproject.toml`).
- Architecture guard: `lint-imports` — ensures `domain` does not import `application`, `api`, or `infrastructure`.
- Lint (optional): `ruff check` — default rules are minimal (`E9`); use `ruff check --extend-select F` for stricter checks when refactoring.

Subprojects under `modules/` (e.g. `rag_service`) remain separate trees; tests add them via `pythonpath` in pytest config. Prefer giving each module its own `pyproject.toml` when you split or publish it.

## Running
1. Start Qdrant (and any optional services required by your setup).
2. Start the RAG proxy/server.
3. Open the WebUI or use the CLI entry point.

If something doesnâ€™t work, see TROUBLESHOOTING.md.
