# ChironAI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/github/v/tag/Rayllienstery/ChironAI?label=version)](https://github.com/Rayllienstery/ChironAI/tags)
[![CI](https://github.com/Rayllienstery/ChironAI/actions/workflows/quality.yml/badge.svg)](https://github.com/Rayllienstery/ChironAI/actions)

ChironAI is a modular RAG (Retrieval-Augmented Generation) platform with a provider-runtime LLM proxy. Core code owns OpenAI/Anthropic-compatible proxy APIs and generic provider contracts; Ollama-specific service, model, and raw API behavior is owned by the bundled `ollama-provider` extension. Default configuration ships with Apple documentation sources (Swift, iOS, SwiftUI), but any domain can be configured through source and prompt settings.

## What it does
- Crawls and indexes documentation sources into a Qdrant collection.
- Accepts user questions through the WebUI and/or CLI.
- Retrieves relevant chunks from Qdrant, optionally reranks them, and produces a grounded answer.

## Core components
- Qdrant: vector database for embeddings and chunk storage.
- LLM provider runtime: extension-backed chat, embeddings, and reranking.
- `ollama-provider`: bundled extension for local Ollama ownership.
- RAG prompts: bundled defaults in `Core/modules/prompts_manager/`; runtime edits in `WebUI/prompts/`.

## Configuration
- Main RAG settings: config/rag.yaml.
- Prompt selection: set `rag.prompt` in config/rag.yaml or override via RAG_PROMPT.

## Development (Python packaging)

Install the **core library** and dev tools from the repository root (editable installs, same idea as local Swift packages):

```bash
pip install -r requirements-dev.txt
```

This installs `chironai` from [`pyproject.toml`](pyproject.toml) (host packages: `application`, `api`, `config`, `core`, `domain`, `infrastructure`) plus bundled support modules discovered by the root package config. For the OpenAI-compatible `/v1` proxy blueprint, also install `pip install -e CoreModules/LlmProxy` (package name `llm-proxy`). Console entry points: `tmrag` / `chironai` → `api.cli`.

- Tests: `pytest` (config in `pyproject.toml`).
- Architecture guard: `lint-imports` — ensures `domain` does not import `application`, `api`, or `infrastructure`.
- Lint (optional): `ruff check` — default rules are minimal (`E9`); use `ruff check --extend-select F` for stricter checks when refactoring.
- Local quality gate: `python scripts/quality_gate.py --profile minimal`. Use `--profile full` before release work; `--profile release --include-advisory` also attempts the long-running startup smoke.

The hexagonal **`rag_service`** package ships with **`chironai_rag`** in **`CoreModules/RagService`** (pip `chironai-rag-service`; see `requirements-dev.txt`). Other subprojects under `modules/` stay on `pythonpath` for pytest as needed.

## Quick start

1. Clone the repository and enter it.
2. Copy the example environment file:
   ```bash
   cp .env.example .env
   ```
3. Start Qdrant and Ollama (optional but recommended for local models):
   ```bash
   docker compose up -d qdrant ollama
   ```
4. Install the Python packages and dev tools:
   ```bash
   pip install -r requirements-dev.txt
   ```
5. Build the frontend and start the server:
   - Windows: `build_and_run.bat`
   - Manual: `npm run build` in `CoreModules/CoreUI`, then run `start_webui.bat` (Windows) or start the Flask app from the repo root.
6. Open `http://127.0.0.1:8080/webui` (or the URL printed by the startup script).

> **Beta security note:** The WebUI currently does not require authentication. Mutating routes such as extension install/remove/enable/disable are exposed to anyone who can reach the WebUI. Run ChironAI only on `localhost` or inside a trusted network until auth is added. See `SECURITY.md` for details.

## Platform support

- **Windows 11 + Docker Desktop** — primary development and test environment. This is where the release quality gate and manual smoke tests are run.
- **Linux / macOS / WSL** — should work via Docker Compose (the runtime image is Debian-based), but I do not personally test there. The CI `linux-fast` job runs a subset of the gate on Ubuntu, so the core backend and Docker build are exercised on Linux. Community feedback and pull requests for other platforms are welcome.

## Running
1. Start Qdrant (and any optional services required by your setup).
2. Start the RAG proxy/server.
3. Open the WebUI or use the CLI entry point.

## Contributing

See [`docs/CONTRIBUTING.md`](docs/CONTRIBUTING.md) for branch conventions, commit style, quality gates, and first-PR guidance.

## Security

If you discover a security vulnerability, please report it privately. See [`SECURITY.md`](SECURITY.md) for supported versions and reporting instructions.

## License

ChironAI is released under the [MIT License](LICENSE).

If something doesn’t work, see [`DEPENDENCIES.md`](DEPENDENCIES.md) and [`docs/QUALITY_GATE_PROFILES.md`](docs/QUALITY_GATE_PROFILES.md).
