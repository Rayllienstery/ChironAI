# ChironAI — Code-Level Improvements

## 1. Domain Layer Duplication (Shim / Re-export Anti-pattern)

- [ ] **Remove the root `domain/` shim layer.** Files like `domain/services/chunking.py`, `domain/services/prompt_builder.py`, `domain/services/rag_trace.py`, `domain/services/rag_trigger.py`, `domain/services/rerank.py`, and `domain/services/retrieval.py` are thin wrappers that do nothing but `from rag_service.domain.services.xxx import *`. This adds indirection without value — a developer reading `domain/services/retrieval.py` has to open `CoreModules/RagService/rag_service/domain/services/retrieval.py` to find the real logic. Pick one canonical location and delete the shim.

- [ ] **Decide which `application/rag/use_cases.py` is canonical.** The root `application/rag/use_cases.py` and `CoreModules/RagService/rag_service/application/use_cases.py` overlap significantly. Both define `search_rag`, `build_rag_context`, `answer_question`, etc. Currently the root one appears more feature-complete (coverage reports, pipeline steps), but the `rag_service` one has its own copy. Consolidate into one, re-export from the other, or delete the stale copy.

- [ ] **Remove `domain/entities/rag.py` import from `rag_service.domain.entities`.** The root `domain/entities/rag.py` does `from rag_service.domain.entities import QueryIntent, RagAnswerResponse, RagChunk, RagContext, RagQuestionRequest`. This means the root `domain` package depends on `CoreModules/RagService`, violating the hexagonal principle that `domain` should be the most independent layer. Entities should live in one place and be imported by outer layers, not the other way around.

- [ ] **Audit all `from rag_service.xxx import *` in root `domain/services/`.** Wildcard re-exports (`# noqa: F401,F403`) hide what symbols are actually available. Replace with explicit imports or delete the shim files entirely.

---

## 2. chat_completions_handler.py — Monolith (~2400 lines)

- [ ] **Decompose `CoreModules/LlmProxy/llm_proxy/chat_completions_handler.py`.** This single file contains:
  - SSE streaming generators (plain text, tool calls, native Gemini)
  - RAG pipeline orchestration (trigger, search, rerank, context assembly)
  - Proxy settings loading and model selection
  - Reasoning content handling
  - Tool call state persistence
  - Metrics and logging
  - Request/response tracing
  Each of these should be a separate module or class. The deeply nested functions (e.g. `generate_sse_native`, `generate_sse_tool_call`, `generate_sse_plain_text`) are a sign it grew organically.

- [ ] **Extract SSE streaming logic into a dedicated module.** The three streaming modes (native Gemini, tool-call, plain-text) share little code but are tangled in the same closure scope. Pull them into `chat_completions_sse.py` or similar.

- [ ] **Extract RAG pipeline orchestration from the handler.** The handler calls `run_merged_docs_step`, `run_web_supplement_step`, builds RAG context, and handles errors — this is use-case logic, not HTTP handler logic. Move to `application/` or a dedicated `rag_orchestrator.py`.

---

## 3. Blurred Boundaries Between Root Modules and CoreModules

- [ ] **Clarify ownership of `application/rag/` vs `CoreModules/RagService/application/`.** Both directories contain `use_cases.py`, `params.py`, and `pipeline_steps/`. A new contributor cannot tell which one is active. Options:
  - Make `rag_service` a pure HTTP shell that imports from root `application.rag`
  - Or move everything into `rag_service` and make root `application/rag` a thin re-export
  Either is fine, but the current ambiguity is technical debt.

- [ ] **Clarify ownership of `infrastructure/` vs `CoreModules/RagService/infrastructure/`.** Root `infrastructure/` has Qdrant, Ollama, crawl, database, metrics, logging. `rag_service/infrastructure/` has its own Qdrant repo, Ollama clients, CLI runner, container. Some are duplicates (qdrant_repository vs rag_repository_impl), some are unique (keyword_collections_sqlite only in rag_service). Document which infra lives where and why.

- [ ] **Audit `api/http/` vs `CoreModules/RagService/api/http.py`.** The root `api/http/` has many route files (rag_routes, proxy_status, proxy_trace, webui_*). The `rag_service` has its own `api/http.py` with a Flask app. Are both deployed? Is one a fallback? Document the deployment topology.

---

## 4. Uneven Module Depth

- [ ] **Flesh out `CoreModules/MdIngestionService`.** It has only `__init__.py`, `api/cli.py`, `application/use_cases.py`, and `domain/entities.py`. Compared to `RagService` (dozens of files across domain/application/infrastructure), this module looks skeletal. Either commit to its scope or document it as a stub.

- [ ] **Flesh out or remove `CoreModules/LlmInteractor`.** It has discovery, install_state, manifest, registry_client, runtime — a promising idea (model discovery + installation), but the implementation is thin. If it is not used, remove it; if it is, add tests and integration.

- [ ] **Review `CoreModules/DockerManager`.** Single `manager.py` file. If it is just a helper for `ServiceStarter`, consider inlining it or merging.

---

## 5. Configuration Sprawl

- [ ] **Consolidate RAG config access.** Settings are read from:
  - `config/rag.yaml`
  - `config/__init__.py` (env overrides)
  - `CoreModules/RagService/rag_service/config.py` (its own loader with `_load_host_repo_overlay`)
  - WebUI settings DB (proxy_settings_contract)
  - `application/rag/params.py` (RAGAnswerParams, RAGDependencies)
  This makes it hard to trace where a parameter like `rag.top_k` actually resolves. Centralize config resolution in one place.

- [ ] **Remove `_load_host_repo_overlay()` magic.** `rag_service/config.py` tries to guess the repo root and load YAML from it. This is fragile and surprising. Config paths should be explicit (env var or CLI arg).

- [ ] **Document all env vars in one place.** Currently they are scattered across `config/__init__.py`, `rag_service/config.py`, `rag_service/runtime.py`, and various `*_handler.py` files. A single `ENV_VARS.md` or a `Config` dataclass with docstrings would help.

---

## 6. Developer Experience Friction

- [ ] **Eliminate `sys.path.insert` hacks.** Multiple entry points (`WebUI/rag_proxy.py`, `WebUI/app.py`, `api/cli/__main__.py`) manipulate `sys.path` to find packages. This breaks in any non-standard setup. Use proper package installs (`pip install -e .`) or `python -m` consistently.

- [ ] **Standardize entry points.** Currently:
  - `python -m api.cli` (CLI)
  - `WebUI/rag_proxy.py` (proxy server)
  - `WebUI/app.py` (web UI)
  - `rag_service` standalone via `python -m rag_service`
  - `ServiceStarter` via `python -m servicestarter`
  Consider a single `chironai` CLI with subcommands: `chironai serve`, `chironai rag`, `chironai crawl`, `chironai start`.

- [ ] **Add a `CONTRIBUTING.md`** explaining the module layout, which packages are canonical, and how to add a new feature without duplicating logic.

---

## 7. Testing Gaps

- [ ] **Add tests for `chat_completions_handler.py`.** At ~2400 lines with complex branching (streaming, RAG, tools, errors), this file has near-zero test coverage. Start with the pure functions (`_truthy_body_flag`, `_positive_int_env`, `_non_empty_str`, `_resolve_trace_chain_id`) and then add integration tests for the main flow.

- [ ] **Add tests for the root `application/rag/use_cases.py`.** The `rag_service` equivalents have tests; the root copies do not.

- [ ] **Add tests for `CoreModules/WebInteraction`.** The module has ranking, caching, search, triggers — but no `tests/` directory inside it.

- [ ] **Add a regression test suite for RAG answers.** The `rag_tests/` framework exists (markdown scenarios + CLI runner), but it is not wired into CI as a pass/fail gate. Make `python -m api.cli rag-tests run` part of CI.

---

## 8. Observability & Operations

- [ ] **Add `/api/embed` probe to health check.** Currently `GET /health` checks Ollama `/api/tags` and Qdrant `/collections`, but not the embed endpoint. A failing embed endpoint silently skips files during indexing (as noted in TODO.md).

- [ ] **Add structured JSON logging to all RAG pipeline steps.** The proxy has tracing, but the root RAG pipeline (`application/rag/use_cases.py`) logs inconsistently. Each step (query prep, embed search, rerank, context assembly) should emit a structured log line with timing and result counts.

- [ ] **Add retry with backoff for Ollama `/api/embed` failures.** Indexing a large docset should not fail on a single transient 500 from Ollama.

---

## 9. Code Quality & Maintenance

- [ ] **Reduce `api/http/webui_routes.py` size.** It is a large file handling many UI endpoints. Split by domain (sources, prompts, sessions, settings, docker, extensions) — the directory already has `webui_crawler_source_routes.py`, `webui_docker_routes.py`, `webui_prompt_routes.py`, `webui_extensions_routes.py`, so the pattern exists. Finish the migration.

- [x] **Remove dead code paths.** Runtime code now imports `should_skip_rag_search` from `rag_trigger`, which owns the trigger heuristic. The `retrieval.py` export remains as a compatibility path, and root `domain/services/retrieval.py` stays as an intentional thin wrapper covered by compat tests rather than a stale implementation.

- [x] **Standardize error handling patterns.** Some modules use custom exception classes (`RetrievalError`, `EmbeddingError`, `RerankError`), others return `None` or empty dicts on failure. Pick one convention per layer.

---

## 10. Security

- [x] **Audit `.gitignore` for secrets.** All required patterns are explicitly covered: `*.db`/`*.sqlite`/WAL sidecars (lines 117–129), `.env`/`.env.*` (lines 65–69), `logs/`/`*.log` (lines 78–80), `*.key`/`*.pem` (lines 72–73). No gaps found.

- [x] **Scan git history for accidentally committed secrets.** Scanned with `git log --all --diff-filter=A` for `*.env`, `*.key`, `*.pem`, `sk-proj-*`, `sk-ant-*`, `password`, `Bearer`. No real secrets ever committed. `api_key.py` matched `sk-` but only contains the internal `chiron_sk_` prefix string — no actual key values. All secret-type file extensions return 0 tracked files in `git ls-files`.

---

*Generated from static code analysis of the repository structure, imports, and module boundaries. Priorities should be validated against actual deployment needs.*
