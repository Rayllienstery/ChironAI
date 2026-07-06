# ChironAI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Version](https://img.shields.io/github/v/tag/Rayllienstery/ChironAI?label=version)](https://github.com/Rayllienstery/ChironAI/tags)
[![CI](https://github.com/Rayllienstery/ChironAI/actions/workflows/quality.yml/badge.svg)](https://github.com/Rayllienstery/ChironAI/actions)
[![codecov](https://codecov.io/gh/Rayllienstery/ChironAI/branch/master/graph/badge.svg)](https://codecov.io/gh/Rayllienstery/ChironAI)

ChironAI lets you run a local/private RAG system over your own documentation, inspect how retrieval works, and extend the runtime through isolated provider modules.

It is aimed at developers who want a debuggable RAG platform rather than a black-box chatbot.

ChironAI is published as a sanitized initial public release. The project was developed privately first, and the previous internal history was intentionally removed before publication to avoid exposing logs, local traces, or accidental sensitive data.

The repository is provided as-is, primarily as a practical reference and reusable foundation for developers who want a transparent local RAG platform.

Under the hood, ChironAI is a modular RAG platform with a provider-runtime LLM proxy. Core code owns OpenAI/Anthropic-compatible proxy APIs and generic provider contracts; Ollama-specific behavior is owned by the bundled `ollama-provider` extension. Default configuration ships with Apple documentation sources (Swift, iOS, SwiftUI), but any domain can be configured through source and prompt settings.

## Why ChironAI?

- **Local-first RAG** with Docker-backed services.
- **Transparent retrieval, reranking, prompting, and answer generation** — you can trace every step.
- **Extension-based provider runtime** instead of hardcoded Ollama/OpenAI logic.
- **Quality gates and architecture checks** designed for AI-assisted development.

## What it does
- Crawls and indexes documentation sources into a Qdrant collection.
- Accepts user questions through the WebUI and/or CLI.
- Retrieves relevant chunks from Qdrant, optionally reranks them, and produces a grounded answer.

## Core components
- Qdrant: vector database for embeddings and chunk storage.
- LLM provider runtime: extension-backed chat, embeddings, and reranking.
- `ollama-provider`: bundled extension for local Ollama ownership.
- RAG prompts: bundled defaults in `Core/modules/prompts_manager/`; runtime edits in `Core/data/webui/prompts/`.

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

> **Security note:** ChironAI binds to `127.0.0.1` by default (`server.yaml` / `SERVER_HOST`). The WebUI has no built-in authentication — any client that can reach the bind address has full management access. Do not expose the WebUI to the public internet; use a trusted network or an authenticating reverse proxy for remote access. See `SECURITY.md` and [ADR 0008](docs/adr/0008-webui-auth-model.md).

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
