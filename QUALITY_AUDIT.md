# ChironAI Quality Audit

Living roadmap for polishing the repository step by step.

Updated: 2026-05-31
Current release target: 0.6.7

This document is the master cleanup map. It is intentionally broader than a
single refactor ticket: use it to choose the next small cleanup pass, verify it,
then update this file as reality changes.

**Passes 1–6 and §5 backlog (through 2026-05-31) are complete.** Further work is
optional hardening only (e.g. simplify config fallbacks in code, remove Qdrant
legacy paths after fleet migration).

---

## 1. Current Baseline

The repo is currently past the obvious static-analysis layer:

- `ruff check --extend-select F` is clean.
- `python -m vulture` is clean.
- `npm run knip` in `CoreModules/CoreUI` is clean.
- Recent focused Python suite passed: `pytest tests\application tests\domain tests\rag_service tests\api tests\webui`.
- Recent CoreUI production build passed: `npm run build`.
- Root RAG application/domain import paths have been collapsed to canonical `rag_service.*`.
- The one-off `scripts/db_analysis.py` SQLite probe was removed.

This means the next cleanup passes should focus on second-order debt:
stale docs, intentional versus accidental compatibility, oversized modules,
duplicate ownership, manual scripts, entrypoint consistency, and guardrails.

---

## 2. Cleanup Principles

- Prefer behavior-preserving cleanup over broad rewrites.
- Delete only when usage is disproven or compatibility is explicitly not public.
- Keep public HTTP compatibility documented and tested before changing it.
- Favor canonical package paths over root shims or wildcard re-exports.
- When a cleanup changes code, bump `core/version.py` and update `CHANGELOG.md`.
- Update tests with the cleanup, not after the cleanup.
- Add guardrails for boundaries that were just cleaned, so old patterns do not return.
- Treat docs as code: stale architecture docs are cleanup targets, not background noise.

---

## 3. Confirmed Completed Work

### RAG canonicalization

- Root RAG shim files were removed:
  - `application/rag/use_cases.py`
  - `application/rag/params.py`
  - `application/container.py`
  - `domain/entities/rag.py`
  - RAG-owned wrappers under `domain/services/`
- Runtime code and tests now import canonical `rag_service.*` paths.
- `prompt_name` support moved into `rag_service.application.params`.
- `rag_service.domain.services.metadata_inference` now owns the metadata helpers previously stranded in root `domain/services`.
- `tests/application/test_rag_import_boundaries.py` guards against reintroducing removed root RAG import paths.

### Static dead code

- `ruff --extend-select F` unused-import findings were cleaned.
- `vulture` findings in tests were cleaned.
- CoreUI JSDoc import that confused `knip` was removed.

### Scripts

- `scripts/db_analysis.py` was removed as a hardcoded one-off local SQLite probe.
- `scripts/sync_bundled_extensions.py` remains live: documented and tested.
- `scripts/build_app.bat` remains live: called by `build_and_run.bat`.
- `scripts/install_dependencies.bat` remains live: documented in `DEPENDENCIES.md`.
- `scripts/audit_apple_ingest_filter.py` remains live enough: manual offline audit with a real `main()`.

---

## 4. Active Cleanup Lanes

### A. Stale Documentation Sync

Risk: low for behavior, high for contributor confusion.

Known stale or partially stale docs:

- [x] `Improvements2.md` — synced with `rag_service.*` canonicalization (2026-05-31).
- [x] `docs/legacy_map.md` — system map uses `rag_service.application.params`.
- [x] `docs/ARCHITECTURE.md` — HTTP/data-flow and container ownership updated.
- [x] `Improvement.md` — ADR and retrieval references updated (2026-05-31).
- [x] `DEPENDENCIES.md` — scripts inventory includes live scripts; `db_analysis.py` removed.
- [x] `docs/EXTENSIONS_GITHUB_MIGRATION.md` — legacy Flask keys documented as compatibility aliases behind accessors (verified 2026-05-31).
- [x] `CoreModules/RagService/README.md` — Ollama provider boundary + legacy `ollama_*` modules clarified.
- [x] `infrastructure/ollama/README.md` — module map and import guardrail (2026-05-31).
- [x] `config/CONFIG_AUTHORITY.md`, `config/ENV_REFERENCE.md` — precedence and env index (2026-05-31).

Likely verification:

- `rg "application/rag/params|application/rag/use_cases|domain/services/retrieval|test_compat_wrappers|db_analysis" -n *.md docs CoreModules modules`
- `ruff check --extend-select F`
- `python -m vulture`

### B. Intentional Compatibility Versus Accidental Legacy

Risk: medium. Compatibility removals can break external clients.

Do not remove yet:

- `/v1/completions`
- prompt/input/suffix compatibility for legacy OpenAI-style clients
- raw Ollama-compatible `/api/tags`
- raw Ollama-compatible `/api/show`
- raw Ollama-compatible `/api/generate`
- raw Ollama-compatible `/api/chat`
- `proxy_settings.rag_collection` fallback
- hash-only legacy proxy API key handling
- RAG test legacy metrics labels for historical runs
- old extension registry local fields used by migration/backcompat tests

Candidate cleanup:

- Name compatibility functions so intentional compat is obvious.
- Move accidental `legacy` comments into either "contract" or "cleanup candidate" buckets.
- Add docs/tests around protected public compatibility surfaces.
- Remove references to already-removed internal root RAG shims.

Likely verification:

- `pytest tests\api tests\application`
- `rg "legacy|compat|backward" -n api application CoreModules infrastructure tests docs`

### C. WebUI Route Monolith — resolved 2026-05-31

Risk: was medium-high; now low after Pass 4.

Composition root:

- `api/http/webui_routes.py` (~255 lines, `register_*` only)

Already split patterns exist:

- `api/http/webui_crawler_routes.py`
- `api/http/webui_crawler_source_routes.py`
- `api/http/webui_docker_routes.py`
- `api/http/webui_extensions_routes.py`
- `api/http/webui_llm_proxy_routes.py`
- `api/http/webui_performance_routes.py`
- `api/http/webui_prompt_routes.py`
- `api/http/webui_session_routes.py`
- `api/http/webui_settings_routes.py`
- `api/http/webui_version_routes.py`

Done (Pass 4): tester, RAG, chat, testing preview, provider helpers extracted; `LLM_PROXY_BUILDS_APP_KEY` re-export kept for tests.

Likely verification:

- `pytest tests\api tests\webui`
- `python -c "import api.http.webui_routes as r; print('routes', len(r.webui_bp.view_functions))"`
- `ruff check --extend-select F api tests\api`

### D. LlmProxy Handler Decomposition

Risk: high. This code carries proxy compatibility, tool calls, streaming, RAG, traces, and budgets.

Current hotspot:

- `CoreModules/LlmProxy/llm_proxy/chat_completions_handler.py`

Candidate extraction order:

1. Pure helpers with direct tests:
   - request option parsing
   - body flag parsing
   - trace-chain id resolution
   - text/reasoning content normalization
2. Response/log shaping helpers.
3. Tool-round state helpers.
4. RAG/web supplement orchestration boundary.
5. Streaming generator extraction only after tests are strong enough.

Protected behavior:

- OpenAI chat response shape.
- SSE chunk order and finish reasons.
- Native tools path.
- Gemini tool/thought signature handling.
- apply-edit and save-file tool argument behavior.
- budget exhaustion warnings.
- proxy trace metadata.

Likely verification:

- `pytest tests\api\test_http_endpoints.py tests\llm_proxy`
- `ruff check --extend-select F CoreModules\LlmProxy tests\llm_proxy tests\api`

### E. Config Authority Sprawl

Risk: medium-high. Config changes can silently alter runtime behavior.

Current sources:

- `config/*.yaml`
- `config/__init__.py`
- `CoreModules/RagService/rag_service/config.py`
- WebUI settings DB
- proxy settings blob
- environment variables

Candidate cleanup:

- Build an explicit config authority table.
- Document env vars in one place.
- Identify which values are app-level, proxy-level, RAG-service-level, or extension-level.
- Reduce duplicated fallback logic only after tests encode precedence.
- Review `_load_host_repo_overlay()` behavior in `rag_service.config`.

Likely verification:

- `pytest tests\config tests\application\test_proxy_settings_contract.py tests\rag_service`
- `rg "get_.*_url|get_.*_model|get_retrieval|get_indexing|get_proxy|os.environ" -n config CoreModules api application`

### F. Scripts And Entrypoints

Risk: low-medium. Scripts are often manually used.

Current scripts:

- `scripts/build_app.bat`: keep, called by `build_and_run.bat`.
- `scripts/install_dependencies.bat`: keep, documented.
- `scripts/sync_bundled_extensions.py`: keep, tested.
- `scripts/audit_apple_ingest_filter.py`: keep for now, document or move to `scripts/dev/` later.

Candidate cleanup:

- Document `audit_apple_ingest_filter.py` in a developer doc or move it to a clearly marked dev/audit area.
- Add `--help` smoke tests for Python scripts with CLIs.
- Decide whether batch entrypoints should be mirrored by `chironai` CLI subcommands.
- Remove empty `scripts/bin` if it remains empty and unreferenced.

Likely verification:

- `python -m vulture scripts tests\scripts`
- `ruff check --extend-select F scripts tests\scripts`
- `pytest tests\scripts`
- `rg "scripts[\\/]|build_app|install_dependencies|sync_bundled_extensions|audit_apple_ingest_filter" -n .`

### G. CoreUI Surface

Risk: medium. Static tools are clean, but UI drift can hide in CSS and service/API shape.

Current clean baseline:

- `npm run knip`
- `npm run build`

Candidate cleanup:

- Audit unused CSS selectors manually by component ownership.
- Review `src/services/api.js` for service methods tied to removed endpoints.
- Check `CoreUIShowcaseTab.jsx` against actual reusable components.
- Verify docs/screens still match current navigation.
- Keep `/api/webui` client methods aligned with `core/contracts/webui_api.py`.

Likely verification:

- `npm run knip`
- `npm run build`
- targeted `rg` for removed endpoint names after each API cleanup

### H. Test And Guardrail Hygiene

Risk: low-medium.

Current guardrails worth preserving:

- RAG canonical import boundary test.
- Ollama migration import allowlist.
- Extension boundary guardrails.
- Docker ownership/audit tests.

Candidate cleanup:

- Remove stale allowlist entries for deleted tests/files.
- Add guardrails when splitting monolith routes.
- Prefer behavior tests over "source contains string" tests when practical.
- Keep fast targeted test commands documented in this file.

Likely verification:

- `pytest tests\application tests\api tests\rag_service`
- `rg "test_compat_wrappers|deleted|allowlist|forbidden|legacy_key" -n tests`

---

## 5. Candidate Backlog

Use this as the queue for future passes. Keep each pass small enough to verify.

| Status | Risk | Candidate | Likely verification | Notes |
|---|---:|---|---|---|
| [x] | Low | Sync stale root RAG shim references in docs | `rg` on `*.md docs` (2026-05-31) | `Improvements2.md`, `Improvement.md`, `ARCHITECTURE.md` |
| [x] | Low | Update `docs/legacy_map.md` system map | `rg "application/rag/params" docs/legacy_map.md` | Points to `rag_service.application.*` |
| [x] | Low | Update `Improvements2.md` completed status | docs grep + static checks | Section 1/3/9 marked done where applicable |
| [x] | Low | Document `scripts/audit_apple_ingest_filter.py` or move to dev scripts | `DEPENDENCIES.md` | Kept in `scripts/`; described as manual offline audit |
| [x] | Low | Remove empty `scripts/bin` if untracked/unreferenced | `rg "scripts/bin"` | Directory does not exist |
| [x] | Medium | Clean stale allowlist entries in Ollama migration guardrails | `pytest tests\application\test_ollama_migration_guardrails.py` | Removed `test_compat_wrappers.py` |
| [x] | Medium | Reclassify root `infrastructure/ollama/*` shims | `pytest tests\application\test_ollama_migration_guardrails.py` | `infrastructure/ollama/README.md`; allowlist → `webui_rag_routes.py` |
| [x] | Medium | Reduce `api/http/webui_routes.py` remaining responsibilities | `pytest tests\webui tests\api -k webui` | Composition root ~255 lines |
| [x] | Medium | Split remaining WebUI tester/model settings routes | `webui_model_tester_routes.py` + `tests\webui` | URLs unchanged |
| [x] | Medium | Add config authority table | `pytest tests\config\test_config_precedence.py` | `config/CONFIG_AUTHORITY.md` |
| [x] | Medium | Create env var reference doc | `pytest tests\config` | `config/ENV_REFERENCE.md` |
| [x] | High | Extract pure helpers from LlmProxy handler | `pytest tests\llm_proxy\test_chat_completions_request_parsing.py` | `chat_completions_request_parsing.py` (2026-05-31) |
| [x] | High | Extract LlmProxy streaming logic | `tests/llm_proxy/test_chat_completions_streaming.py` + API tests | `chat_completions_streaming.py` (2026-05-31) |
| [x] | High | Review Qdrant vector modes (legacy paths removed) | `pytest tests\rag_service\test_qdrant_vector_modes.py` | Named `dense` + hybrid only |
| [x] | Medium | Review CoreUI API service methods after route cleanup | `npm run knip`; `npm run build` | `CoreModules/CoreUI/docs/WEBUI_API.md` (2026-05-31) |

---

## 6. Suggested Execution Order

### Pass 1: Docs Truth Sync — done 2026-05-31

Goal: make docs match the current code after RAG canonicalization and scripts cleanup.

Done:

- Updated `Improvements2.md`, `Improvement.md`, `docs/legacy_map.md`, `docs/ARCHITECTURE.md`, `DEPENDENCIES.md`.
- Linked `QUALITY_AUDIT.md` from `docs/legacy_map.md` and `Improvements2.md`.

Verify:

- `rg "application/rag/use_cases|application/rag/params|domain/services/retrieval|test_compat_wrappers|db_analysis" -n *.md docs CoreModules`
- `ruff check --extend-select F`
- `python -m vulture`

### Pass 2: Guardrail Cleanup — done 2026-05-31

Goal: remove stale allowlist entries and strengthen boundaries.

Done:

- Removed `test_compat_wrappers.py` from Ollama migration allowlist.

Done:

- Ollama import allowlist updated (`webui_rag_routes.py` replaces removed `webui_routes` import).
- No `test_compat_wrappers` references remain in guardrail allowlists.

Verify:

- `pytest tests\application`
- `pytest tests\api\test_extensions_boundary_guardrails.py`

### Pass 3: Entrypoint And Scripts Polish — done 2026-05-31

Goal: make every script either documented, tested, or removed.

Done:

- `audit_apple_ingest_filter.py` documented in `DEPENDENCIES.md`; added `--help` via argparse.
- Script inventory in `DEPENDENCIES.md`.
- `tests/scripts/test_script_cli_smoke.py` for `--help` on Python CLIs.

Verify:

- `pytest tests\scripts`
- `python -m vulture scripts tests\scripts`
- `ruff check --extend-select F scripts tests\scripts`

### Pass 4: WebUI Route Thinning — done 2026-05-31

Goal: continue reducing `webui_routes.py` without API drift.

Done:

- `api/http/webui_model_tester_routes.py` — model settings + Model Tester.
- `api/http/webui_rag_routes.py` — RAG settings, pipeline diagram, Qdrant status/collections/start/stop, dashboard-metrics.
- `api/http/webui_chat_routes.py` — `/models`, `/config`, `/chat`, `/dev-console`.
- `api/http/webui_provider_helpers.py` — shared provider catalog + runtime chat/embed helpers.
- `api/http/webui_testing_routes.py` — `/testing/external-docs/preview`.
- `webui_routes.py` — composition root (~255 lines); re-exports `LLM_PROXY_BUILDS_APP_KEY` for test monkeypatch compat.
- `webui_llm_proxy_routes.py` / `webui_crawler_routes.py` import provider + Qdrant helpers from shared modules (no duplicate implementations).

Verify:

- `pytest tests\api tests\webui`
- `npm run build`

### Pass 5: LlmProxy Pure Helper Extraction — done 2026-05-31

Goal: reduce handler size with low behavioral risk.

Done:

- `truthy_body_flag`, `positive_int_env`, `non_empty_str`, `resolve_trace_chain_id` in
  `llm_proxy/chat_completions_request_parsing.py`.
- Response/message helpers in `llm_proxy/chat_completions_response_helpers.py`.
- Handler helpers in `llm_proxy/chat_completions_handler_helpers.py` (`build_forced_think_value`,
  pipeline trace append, proxy settings load, rerank model apply, RAG completion log payload).
- Tests in `tests/llm_proxy/test_chat_completions_*_helpers.py`.

Out of scope (stay in `chat_completions_handler.py` until a dedicated pass):

- RAG orchestration boundary, tool-loop main loop.

Streaming SSE formatting and Ollama event bridging live in `llm_proxy/chat_completions_streaming.py`.

Verify:

- `pytest tests\llm_proxy tests\api\test_http_endpoints.py`
- `ruff check --extend-select F CoreModules\LlmProxy tests\llm_proxy tests\api`

### Pass 6: Config Authority — done 2026-05-31

Goal: document and then reduce config ambiguity.

Done:

- `config/CONFIG_AUTHORITY.md` — authority table per config family and resolution layers.
- `config/README.md` links to the authority doc.
- `tests/config/test_config_precedence.py` locks env-over-YAML for RAG, retrieval, models, Qdrant.

Deferred (no behavior change in this pass):

- Simplify duplicated fallback logic in code after precedence tests guard regressions.

Verify:

- `pytest tests\config tests\application tests\rag_service`

---

## 7. Do Not Remove Yet

These are protected until a dedicated deprecation or compatibility plan says otherwise:

- `/v1/chat/completions`
- `/v1/messages`
- `/v1/responses`
- `/v1/completions`
- `/api/tags`
- `/api/show`
- `/api/generate`
- `/api/chat`
- prompt/suffix/input normalization for legacy clients
- Ollama provider-runtime fallback to direct upstream paths
- `proxy_settings.rag_collection` fallback
- historical RAG test metric version labels
- Open WebUI extension compatibility behavior
- bundled extension bootstrap/offline mirrors

---

## 8. Useful Commands

Static baseline:

```powershell
ruff check --extend-select F
python -m vulture
```

CoreUI:

```powershell
cd CoreModules\CoreUI
npm run knip
npm run build
```

Focused Python baseline:

```powershell
pytest tests\application tests\domain tests\rag_service tests\api tests\webui
```

Scripts:

```powershell
python -m vulture scripts tests\scripts
ruff check --extend-select F scripts tests\scripts
pytest tests\scripts
```

Docs drift searches:

```powershell
rg "application/rag/use_cases|application/rag/params|domain/services/retrieval|test_compat_wrappers|db_analysis" -n *.md docs CoreModules
rg "legacy|compat|backward|shim|wrapper|monolith|temporary" -n api application CoreModules infrastructure tests docs
```

Git review:

```powershell
git status --short
git diff --stat
```

---

## 9. Maintenance Rule

When a cleanup pass finishes:

- Mark the candidate done or update its wording.
- Add any new risk discovered during implementation.
- Record the verification command that actually passed.
- Keep version and changelog aligned with `AI_RULES.md`.
