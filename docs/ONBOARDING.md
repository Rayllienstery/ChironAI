# ChironAI Onboarding

This guide gets a new contributor from a fresh checkout to a first small pull
request.

## 1. Read the Map

Start with these files:

- `README.md` for the product overview and basic commands.
- `AI_RULES.md` for repository terminology, ownership rules, and high-risk
  areas.
- `docs/ARCHITECTURE.md` for layers, module boundaries, and data flow.
- `docs/MODULAR_STRUCTURE.md` for the target modular layout.
- `docs/legacy_map.md` for migration tails and known risks.
- `docs/adr/` for accepted architectural decisions.
- `docs/QUALITY_GATE_PROFILES.md` for local and CI gate profiles.
- `docs/RUNBOOK.md` for diagnostics and recovery when startup, RAG, proxy, or
  extension flows fail.

Keep the vocabulary straight:

- `CoreUI` is the React/Vite app in `CoreModules/CoreUI/`.
- `WebUI/` is runtime data, not the frontend source.
- Web UI HTTP APIs live under `/api/webui`.
- Open WebUI is a separate Docker product owned through the extension system.

## 2. Install the Python Environment

From the repository root:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements-dev.txt
pip install -e CoreModules/LlmProxy
```

The root package exposes the `chironai` and `tmrag` console entry points. The
LlmProxy editable install is needed for the OpenAI-compatible `/v1` blueprint.

Verify the Python side:

```bash
pytest -q -m fast --maxfail=1
python scripts/check_version_drift.py
```

## 3. Install the CoreUI Environment

From `CoreModules/CoreUI`:

```bash
npm install
npm run build
npm run test:run
```

CoreUI talks to the backend over HTTP. Do not import Python, RAG, crawler, or
extension internals into browser code.

## 4. Start the App

For a local startup smoke from the repository root:

```bat
.\build_and_run.bat
```

Success means the log reaches `Server ready` and opens
`http://127.0.0.1:8080/webui`. The script starts a long-running backend; stop it
when you are done.

## 5. Pick a First Issue

Good first changes are:

- Documentation updates that point to existing source-of-truth docs.
- Focused tests for an existing component or helper.
- Small route or CoreUI fixes with targeted tests.
- Roadmap tasks from `Way to 1000.md` whose dependencies are already complete.

Avoid first changes in high-risk areas unless paired with a focused test plan:

- LlmProxy compatibility.
- WebUI API sync.
- Qdrant/RAG retrieval behavior.
- Docker-managed extension services.
- Root layout and module migration.

## 6. Make the Change

Before editing, inspect nearby code and tests. Follow existing local patterns
instead of introducing parallel abstractions.

For CoreUI:

- Use `CoreUIPillTabs` for primary tab strips outside cards.
- Use `CoreUISubtabs` for compact subtabs inside cards or panels.
- Use tokens and existing CSS classes.
- Update showcase coverage when adding or removing reusable UI patterns.

For Python:

- Keep `Core/domain/` free of `api`, `application`, and `infrastructure`
  imports.
- Keep host composition under `Core/`.
- Keep reusable apps and libraries under `CoreModules/`.
- Prefer public contracts and HTTP boundaries over implementation imports.

## 7. Verify Locally

Choose the narrowest useful gate first, then broaden as risk increases:

```bash
pytest -q tests/path/to/test.py --maxfail=1
ruff check path/to/changed_file.py
python -m py_compile path/to/changed_file.py
python scripts/quality_gate.py --profile minimal
```

For CoreUI:

```bash
npm --prefix CoreModules/CoreUI run build
npm --prefix CoreModules/CoreUI run test:run
npm --prefix CoreModules/CoreUI run lint
```

For API changes:

```bash
python scripts/check_api_drift.py --strict --strict-openapi
python scripts/validate_openapi.py
```

For non-documentation changes, also run `build_and_run.bat` and confirm
`Server ready`.

## 8. Open the Pull Request

Use `.github/pull_request_template.md`. Include:

- What changed.
- Why it changed.
- The task ID, if any.
- Commands run and their results.
- Any skipped checks and why.
- Any unrelated failures observed.

## 9. Architecture Quick Links

- `docs/adr/0001-layered-architecture.md` - host layer rules.
- `docs/adr/0002-extension-system.md` - extension model.
- `docs/adr/0003-llm-proxy-compat.md` - compatibility promises.
- `docs/adr/0004-modular-migration.md` - modular migration approach.
- `docs/adr/0005-docker-contract.md` - Docker runtime contract.
- `docs/adr/0006-operational-knowledge.md` - operational docs ownership.

## 10. CoreModule Walkthrough

Use this quick pass before changing a module:

| Module | Entry flow | Key files | High-risk checks |
|--------|------------|-----------|------------------|
| `CoreModules/CoreUI` | Browser loads Vite build, then calls `/api/webui/*` over HTTP. | `src/App.jsx`, `src/services/api.js`, `src/components/`, `src/styles/` | Run `npm run build`; keep API client/types synced with OpenAPI; do not import backend internals. |
| `CoreModules/LlmProxy` | `/v1/*` requests enter Flask blueprint and normalize to provider-backed chat. | `llm_proxy/v1_blueprint.py`, `chat_completions_handler.py`, `wire_format/` | Run `pytest tests/llm_proxy --maxfail=1`; preserve streaming/tool/vision compatibility. |
| `CoreModules/RagService` | RAG use cases build context through embed, search, rerank, and chat provider runtime. | `rag_service/application/use_cases.py`, `infrastructure/qdrant_repository.py`, `runtime.py` | Run targeted RAG tests; keep dense/hybrid vector modes aligned with docs. |
| `CoreModules/DockerManager` | Host and extensions request container lifecycle through the Docker runtime contract. | Docker runtime package, `Core/core/contracts/docker_runtime.py` | Extensions must not shell out to Docker; run extension Docker policy tests. |
| `CoreModules/LogsManager` | Internal scripts read completed proxy journal rows from `logs/webui.db`. | `logs_manager/`, `CoreModules/LogsManager/README.md` | Read-only only; no `/api/webui` or CoreUI surface. |
| `CoreModules/ExtensionsHost` | Host wires extension providers, capabilities, and runtime metadata. | `extensions_host/wiring.py`, extension manifests | Keep manifest capabilities explicit and iframe/schema UI self-contained. |
| `CoreModules/ExtensionsSandbox` | Extension code runs in a constrained worker process. | `extensions_sandbox/` | Keep sandbox boundaries narrow; use security tests before relaxing access. |
| `CoreModules/Security` | Audits extension code and shared security helpers. | `chironai_security/extension_audit.py` | Update tests when adding allowed/blocked patterns. |
| `CoreModules/ErrorManager` | Shared error taxonomy and normalization. | `error_manager/` | Avoid leaking module-specific details into shared categories. |
| `CoreModules/MdIngestionService` | Markdown ingestion and chunk preparation for indexing. | Module README and ingestion package | Verify parser/indexing tests for content changes. |
| `CoreModules/WebInteraction` | Optional web snippets and trigger heuristics for proxy supplements. | Module README, web interaction package | Keep network access optional and gated by settings/env. |
| `CoreModules/OllamaInteractor` | CLI boundary for Ollama HTTP calls. | `ollama_interactor/cli.py`, `ollama_http.py` | Host app should call it as a process boundary; app-owned Ollama UX belongs to the extension. |

When in doubt, open the module README first, then inspect the caller at the
host boundary. Most regressions come from skipping the boundary and importing a
neighbor module's implementation directly.
