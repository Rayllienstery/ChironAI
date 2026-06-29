# ChironAI Runbook

Operational runbook for common local and CI incidents. Use it with
`docs/ARCHITECTURE.md`, `docs/legacy_map.md`, and `AI_RULES.md`; this file is
for symptoms, diagnostics, expected signals, and recovery.

## Baseline Checks

From the repository root:

```bash
python scripts/check_version_drift.py
python scripts/check_api_drift.py --strict --strict-openapi
python scripts/quality_gate.py --profile minimal --list
```

For startup:

```bat
.\build_and_run.bat
```

Expected startup signals:

- `CoreUI build is up to date` or a successful `npm run build`.
- `Starting backend on port 8080...`
- `WebUI: http://127.0.0.1:8080/webui`
- `Server ready`

`build_and_run.bat` starts a long-running server. For automated smoke checks,
capture stdout/stderr, wait for `Server ready`, then stop only the launched
`cmd.exe /c .\build_and_run.bat`, `python -m webui_backend.rag_proxy`, and
`python -m extensions_sandbox.worker` processes.

## Qdrant Unavailable

Symptoms:

- RAG status is down in CoreUI.
- `/health` reports degraded dependency status.
- RAG indexing or retrieval errors mention Qdrant connection failures.

Diagnostics:

```bash
docker ps
docker compose config
python -m pytest tests/rag_service/test_qdrant_vector_modes.py -q
```

Check code ownership before changing behavior:

- WebUI service actions: `Core/api/http/service_control.py`
- RAG runtime: `CoreModules/RagService/rag_service/runtime.py`
- Collection listing: `Core/infrastructure/qdrant/collection_names.py`
- Vector mode behavior:
  `CoreModules/RagService/rag_service/infrastructure/qdrant_repository.py`

Recovery:

- If using compose, start dependencies with `docker compose up qdrant`.
- If Qdrant is reachable but collections are missing, inspect the indexer logs
  and rerun the relevant crawl/index flow.
- Do not add direct Qdrant control to CoreUI or route composition; delegate
  through RagRuntime/service-control boundaries.

## Extension Does Not Start

Symptoms:

- Extension tab is missing or reports an unavailable service.
- Docker actions fail for bundled extensions.
- Extension host bootstrap warnings appear during startup.

Diagnostics:

```bash
python -m pytest tests/llm_interactor/test_extension_docker_policy.py -q
python -m pytest tests/llm_interactor/test_extension_docker_contract_audit.py -q
```

Inspect:

- Extension manifest: `extensions/bundled/<id>/chironai-extension.json`
- Backend provider entry point: `create_provider(host_context, manifest)`
- Host bridge: `CoreModules/ExtensionsHost/`
- Extension backend: `Core/modules/extensions_backend/`
- Docker contract: `docs/adr/0005-docker-contract.md`

Recovery:

- Confirm the manifest declares the capability that the provider uses.
- Confirm Docker-owned services use `host_context.docker_runtime` and
  `DockerContainerSpec`; extensions must not call Docker directly.
- If an extension was extracted to its own repository, treat
  `extensions/bundled/*` as the trusted bootstrap mirror, not the canonical
  development source.

## Proxy Or Compatibility Error

Symptoms:

- IDE agent calls to `/v1/chat/completions`, `/v1/messages`, or `/v1/responses`
  fail or stream malformed chunks.
- Tool calls, image parts, or model listing regress.
- RAG Fusion proxy journal shows a failed provider call.

Diagnostics:

```bash
python -m pytest tests/llm_proxy --maxfail=1 -q
```

Use LogsManager for completed proxy requests:

```python
from logs_manager import get_logs_manager

mgr = get_logs_manager()
latest = mgr.get_latest_log()
matched = mgr.find_latest_log_with_user_message("prompt fragment")
```

Inspect `metadata.trace`, `metadata.trace_id`, `metadata.rag_steps`,
`metadata.rag_context`, and `metadata.response_preview`. `user_query` is
truncated to 500 characters when persisted. LogsManager does not read in-memory
live traces; use `recent_proxy_traces()` from `Core/api/http/proxy_trace.py`
for active snapshots.

Ownership:

- Compatibility surface: `CoreModules/LlmProxy/`
- Wire-format helpers: `CoreModules/LlmProxy/llm_proxy/wire_format/`
- Provider runtime boundary: `Core/core/contracts/llm_runtime.py`
- Ollama-native behavior: `ollama-provider` extension

Recovery:

- Keep raw Ollama behavior out of core routes.
- Add or adjust focused `tests/llm_proxy` coverage before changing wire-format
  logic.
- If provider runtime is unavailable, fix extension/runtime registration rather
  than adding a direct `localhost:11434` fallback.

## API Drift Or OpenAPI Failure

Symptoms:

- `check_api_drift.py` fails.
- CoreUI generated API types differ from the OpenAPI spec.
- Swagger/OpenAPI validation fails in CI.

Diagnostics:

```bash
python scripts/check_api_drift.py --strict --strict-openapi
python scripts/validate_openapi.py
npm --prefix CoreModules/CoreUI run gen:types
```

Recovery:

- For `/api/webui` changes, keep these synchronized in the same change:
  `Core/core/contracts/webui_api.py`, Flask routes/RESTX models, generated
  OpenAPI docs, and `CoreModules/CoreUI/src/services/api.js` or generated
  types.
- For docs-only OpenAPI reference drift, run the generator in check mode first:
  `python scripts/gen_api_docs.py --check`.

## Startup Smoke Fails Before Server Ready

Symptoms:

- `build_and_run.bat` exits early.
- CoreUI build fails.
- Backend import fails before `Server ready`.

Diagnostics:

```bash
npm --prefix CoreModules/CoreUI run build
python -m py_compile Core/modules/webui_backend/webui_backend/app.py
python scripts/quality_gate.py --profile minimal --list
```

Recovery:

- Fix CoreUI parser/build errors before inspecting backend startup.
- If startup leaves listeners behind, stop only the launched smoke processes or
  use the project helper that clears known WebUI ports.
- Report exact first failing line from stdout/stderr; do not rely only on
  `/health`, which may wait on dependencies such as Qdrant.

## Useful Logs And Data

- Runtime DB: `logs/webui.db`
- CoreUI frontend build: `CoreModules/CoreUI/dist/`
- Startup smoke logs: `tmp/build_and_run_smoke.log` and
  `tmp/build_and_run_smoke.err.log` (written by `scripts/startup_smoke_bat.ps1`)
- Windows startup smoke script: `scripts/startup_smoke_bat.ps1` (starts the
  server, polls `/api/webui/version`, and exits without stopping the app)
- RAG test fixtures: `rag_tests/`
- Proxy journal: persisted rows read by `CoreModules/LogsManager`

Generated artifacts such as `dist/`, coverage reports, and smoke logs should
usually stay out of source changes.
