# ChironAI

ChironAI is a modular RAG (Retrieval-Augmented Generation) platform with a provider-runtime LLM proxy. Core code owns OpenAI/Anthropic-compatible proxy APIs and generic provider contracts; Ollama-specific service, model, and raw API behavior is owned by the bundled `ollama-provider` extension. Configured by default for Apple platforms (Swift, iOS, SwiftUI), but supports any domain through source and prompt configuration.

## What it does
- Crawls and indexes documentation sources into a Qdrant collection.
- Accepts user questions through the WebUI and/or CLI.
- Retrieves relevant chunks from Qdrant, optionally reranks them, and produces a grounded answer.

## Core components
- Qdrant: vector database for embeddings and chunk storage.
- LLM provider runtime: extension-backed chat, embeddings, and reranking.
- `ollama-provider`: bundled extension for local Ollama ownership.
- RAG prompts: versioned system prompts in prompts/.

## Configuration
- Main RAG settings: config/rag.yaml.
- Prompt selection: set `rag.prompt` in config/rag.yaml or override via RAG_PROMPT.

## Development (Python packaging)

Install the **core library** and dev tools from the repository root (editable installs, same idea as local Swift packages):

```bash
pip install -r requirements-dev.txt
```

This installs `chironai` from [`pyproject.toml`](pyproject.toml) (packages: `application`, `api`, `config`, `core`, `domain`, `infrastructure`, `utils`) plus `ollama-interactor`. For the OpenAI-compatible `/v1` proxy blueprint, also install `pip install -e CoreModules/LlmProxy` (package name `llm-proxy`). Console entry points: `tmrag` / `chironai` → `api.cli`.

- Tests: `pytest` (config in `pyproject.toml`).
- Architecture guard: `lint-imports` — ensures `domain` does not import `application`, `api`, or `infrastructure`.
- Lint (optional): `ruff check` — default rules are minimal (`E9`); use `ruff check --extend-select F` for stricter checks when refactoring.
- Local quality gate: `python scripts/quality_gate.py --profile minimal`. Use `--profile full` before release work; `--profile release --include-advisory` also attempts the long-running startup smoke.

The hexagonal **`rag_service`** package ships with **`chironai_rag`** in **`CoreModules/RagService`** (pip `chironai-rag-service`; see `requirements-dev.txt`). Other subprojects under `modules/` stay on `pythonpath` for pytest as needed.

## Running
1. Start Qdrant (and any optional services required by your setup).
2. Start the RAG proxy/server.
3. Open the WebUI or use the CLI entry point.

If something doesn’t work, see TROUBLESHOOTING.md.
