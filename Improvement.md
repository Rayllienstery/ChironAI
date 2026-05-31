# ChironAI — Assessment, Risks, and Improvements

Text in English; module names, env vars, endpoints, and paths — in English, as in the code. For the module map, see [review.md](review.md). **Order of work:** §5 (P0–P3 scale and urgency) → §6 (backlog steps 1–13) → §7 (iterations A–G); the current next step is indicated at the end of §7.

## 1. Objective Assessment (Scale 1–5)

| Axis | Score | Comment |
| :--- | :--- | :--- |
| Architecture and Layers | **4** | Explicit hexagonal split (`domain` / `infrastructure` / `application`), contracts in `core/contracts`, separate installable CoreModules. RAG canon now lives in `rag_service.*`; root `application/rag/` keeps monolith-boundary helpers only. |
| Configurability | **4** | YAML in `config/` + wide env overrides ([`config/__init__.py`](config/__init__.py), [`config/README.md`](config/README.md)). Some parameters are still scattered across the code and WebUI settings. |
| Observability | **2–3** | Logging exists; Prometheus metrics in proxy; `GET /health` checks Ollama+Qdrant via [`infrastructure/stack_health.py`](infrastructure/stack_health.py) on the main app, build proxy, and `rag_service`. Full JSON log on all chat branches and probe `/api/embed` in health — see checklist §6.1. |
| Tests | **3–4** | Pytest covers domain, llm_proxy, rag_service, crawler, md ingestion, web_interaction, part of infrastructure. No single "golden set" of LLM answer regression in CI as a separate artifact (see TODO). |
| Developer experience | **3** | Many entry points (`webui_backend.rag_proxy`, `webui_backend.app`, `api.cli`, standalone `rag_service.api.http`). Repeated `sys.path.insert` complicates onboarding. |
| Secret security | **3** | Keys by meaning via env; [`TODO.md`](TODO.md) explicitly notes strengthening `.gitignore` for DB, logs, `.env`. Periodic audit of commits is needed. |
| Documentation | **3** | README of root and modules are good; no single CHANGELOG in root (noted in TODO). |

**Summary (subjective, one paragraph):** the project is at the level of a **mature beta**: architectural decomposition is strong, RAG and proxy functionality is rich, test base is wider than average for such repositories. Main gaps are operational transparency (health/metrics/structured logs), simplifying launch without manual PYTHONPATH, and finishing second-order debt tracked in [`QUALITY_AUDIT.md`](QUALITY_AUDIT.md) (WebUI route thinning, LlmProxy handler split, config authority).

## 2. Strengths

1. **Clear separation of ports and implementations** — [`domain/ports/__init__.py`](domain/ports/__init__.py), Qdrant/Ollama compatibility adapters in root `infrastructure/`, RAG assembly in [`rag_service.infrastructure.container`](CoreModules/RagService/rag_service/infrastructure/container.py).
2. **OpenAI- and Anthropic-compatible proxy** — [`CoreModules/LlmProxy`](CoreModules/LlmProxy), wiring in [`api/http/llm_proxy_wiring.py`](api/http/llm_proxy_wiring.py): RAG, tools, streaming, autocomplete model, build presets.
3. **Versioned system prompts** — files in `prompts/`, switching via `rag.prompt` / `RAG_PROMPT` ([`config/rag_prompts.py`](config/rag_prompts.py)).
4. **Advanced retrieval** — hybrid / sparse, query expansion, RRF, rerank, filters by `doc_type` and intent (see [`rag_service.domain.services.retrieval`](CoreModules/RagService/rag_service/domain/services/retrieval.py) and [`TODO.md`](TODO.md) for already closed items).
5. **Web supplement without paid APIs** — [`CoreModules/WebInteraction`](CoreModules/WebInteraction), explicit rules "not to mix with RAG" in the fallback prompt text.
6. **Contracts between services** — `core/contracts/*` and README `webui_backend` describe the target HTTP boundary.
7. **RAG Tests as formalized regression** — markdown scenarios + CLI `python -m api.cli rag-tests run` ([`rag_tests/README.md`](rag_tests/README.md)).

## 3. Critical and High Risks

### 3.1 Operations and Dependencies on Local Services

- Failures of **Ollama `/api/embed`** (500) lead to indexing failure of individual files; [`TODO.md`](TODO.md) records real examples. Retries, backpressure, and explicit reporting of "how much skipped due to embed" are needed (checklist step 3, §6.1).
- **`GET /health`** uses common [`check_stack_health()`](infrastructure/stack_health.py): HTTP probes to Ollama (`/api/tags`) and Qdrant (`/collections`), response `status: healthy|unhealthy`, `components`, `503` on failure. Connected in [`api/http/rag_routes.py`](api/http/rag_routes.py) (`service: rag_proxy`) and [`rag_service/api/http.py`](CoreModules/RagService/rag_service/api/http.py) (`service: rag_service`). Optional: separate check of `/api/embed` in health — in checklist §6.1.

### 3.2 Duplication and Divergence of Behavior

**ADR (RAG canon, 2026-05):** use cases, params, entities, and retrieval services live under **`rag_service.application`** and **`rag_service.domain`**. Root `application/rag/` keeps monolith HTTP helpers (for example `proxy_settings_contract`). Removed root shims: `application/rag/use_cases.py`, `application/rag/params.py`, `application/container.py`, and RAG wrappers under `domain/services/`. Guardrail: [`tests/application/test_rag_import_boundaries.py`](tests/application/test_rag_import_boundaries.py). Cleanup roadmap: [`QUALITY_AUDIT.md`](QUALITY_AUDIT.md).

### 3.3 Launch Fragility

- Multiple **`sys.path`** insertions in [`api/http/rag_routes.py`](api/http/rag_routes.py), [`llm_proxy_wiring.py`](api/http/llm_proxy_wiring.py), [`webui_routes.py`](api/http/webui_routes.py), and WebUI backend entry points. CWD error or launch from the "wrong" directory breaks imports.
- **`external_docs_rag`** is optional: `ImportError` is silenced in wiring — useful for dev, but complicates diagnosis of "why no merged context".

### 3.4 WebUI Backend Maintainability

- File [`api/http/webui_routes.py`](api/http/webui_routes.py) is **very large** (thousands of lines). This increases the risk of regressions, complicates review and testing. Target architecture in [`modules/webui_backend/README.md`](modules/webui_backend/README.md) (layers + HTTP clients to services) has not yet fully replaced the monolith.

### 3.5 External Unstable Dependencies

- **DuckDuckGo** and search result parsing may change; the project honestly documents this in WebInteraction README. Risk: sudden degradation of web supplement without process crash.

## 4. Technical Debt

| Topic | Details |
| :--- | :--- |
| Static typing | In [`TODO.md`](TODO.md): mypy/pyright on key modules. Many `type: ignore` and optional-import fallbacks remain in HTTP wiring modules. |
| Linting | Ruff limited to `E9` in [`pyproject.toml`](pyproject.toml); "real" pyflakes/F not enabled by default. |
| Comment language | Mixture of Russian and English in code and TODO; for open-source and uniformity with prompts, English is preferred in new changes. |
| Version documentation | In TODO: root CHANGELOG, extended README. |
| `.gitignore` | Explicitly check ignoring of sqlite, logs, `.env`, crawl artifacts (item in TODO). |

## 5. Priority and Urgency Scale

We use **two axes**: impact on prod/operations (P0–P3) and **timeframe** when it's reasonable to take into work.

| Level | Priority | Urgency | Meaning |
| :--- | :--- | :--- | :--- |
| **P0** | Critical | **Immediately** | False "healthiness" of service, blind spots during incidents; fix first. |
| **P1** | High | **1–2 weeks** | Visibility of failures and debugging (indexing, request logs); significantly reduces investigation time. |
| **P2** | Medium | **2–6 weeks** | Architectural debt and DX; planned by sprints, without blocking releases. |
| **P3** | Low | **As touched / backlog** | Code quality and documentation; does not block functionality. |

## 6. Backlog of Steps (1–13)

### 6.1 Operations and Observability (P0–P1)

1. **[P0] Health: probe `/api/embed`** — add a real embedding call (e.g., of the word "health") to `check_stack_health`. If Ollama is alive but embed fails, the service is `unhealthy`.
2. **[P1] Indexer reporting** — in `md_indexer` or `ingest_markdown_local`, collect and return `indexed_count`, `skipped_count`, `failed_count` + list of errors. Show in UI.
3. **[P1] Embed retry/backoff** — add `tenacity` or manual retry for Ollama embedding calls to handle transient 500s.
4. **[P1] Structured logs in RAG pipeline** — each step of `application.rag.use_cases` (search, rerank, assembly) must emit a JSON log with `latency_ms` and `result_count`.

### 6.2 Architecture and Consolidation (P2)

5. **[P2] Consolidate `rag_service` use cases** — finalize the transition to re-exporting `application.rag.use_cases`. Remove duplicate logic.
6. **[P2] Consolidate `domain` entities** — move `QueryIntent`, `RagChunk`, etc., to a single place (e.g., `core/entities` or root `domain/entities`) and re-export.
7. **[P2] Split `webui_routes.py`** — move routes to Blueprints by domain (crawler, settings, logs, proxy).
8. **[P2] Decompose `chat_completions_handler.py`** — extract RAG orchestration, tool bridging, and streaming into separate modules.

### 6.3 Quality and DX (P2–P3)

9. **[P2] RAG quality baseline** — fix a "golden set" of 20–30 questions and expected chunks. Run `rag-tests` in CI.
10. **[P2] Standardize entry points** — create a single `chironai` CLI (or `python -m api.cli`) that covers all scenarios (serve, ingest, test).
11. **[P3] English comments** — translate remaining Russian comments in `CoreModules` and root.
12. **[P3] Type hints** — add `pyright` to CI for `domain` and `application` layers.
13. **[P3] Root CHANGELOG** — start recording changes by version.

## 7. Iterations (A–G)

- **Iteration A (Observability):** Steps 1, 2, 4. Result: we see why indexing fails and how long RAG steps take.
- **Iteration B (Resilience):** Step 3. Result: indexing is less dependent on transient Ollama glitches.
- **Iteration C (Cleanup):** Steps 7, 8. Result: backend code is readable and testable.
- **Iteration D (Consolidation):** Steps 5, 6. Result: no "drift" of behavior between standalone `rag_service` and proxy.
- **Iteration E (Quality):** Step 9. Result: we know if a prompt change broke retrieval.
- **Iteration F (DX):** Step 10. Result: easy start for new developers.
- **Iteration G (Maintenance):** Steps 11, 12, 13. Result: project is ready for open-source / long-term support.

---
**Next step:** Iteration A, Step 1 (Health probe for `/api/embed`).
