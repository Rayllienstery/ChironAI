# ChironAI: Strict Project Review

Date: 2026-05-04  
Audit: Static repository audit + `pytest` + alignment with external best practices  
Test Results: `492 passed in 4.64s` + `npm.cmd run build` for CoreUI

## Executive Summary

**Thesis: ChironAI already looks like a mature beta platform, not a prototype.**  
Explanation: The project has a modular RAG architecture, OpenAI/Anthropic-compatible proxy, Qdrant, Ollama, WebUI, crawler, ingestion, regression tests for RAG, and separate CoreModules. Having 492 passing tests and a green frontend build is a strong signal of discipline.

**Thesis: The main risk of the project is not a lack of features, but excessive complexity and incomplete migration.**  
Explanation: Legacy layers `api/application/domain/infrastructure` live alongside new `CoreModules/*`, new `modules/*`, thin wrappers, and old monolithic routes. This is normal for an active migration but dangerous for long-term maintenance.

**Thesis: The RAG approach is chosen correctly: dense + sparse + rerank + trace.**  
Explanation: Qdrant explicitly recommends hybrid retrieval and reranking as a way to combine recall and precision, and the project already has `hybrid_sparse_enabled`, RRF merge, rerank pool, coverage gate, and pipeline trace.

**Thesis: Operational readiness is lower than architectural maturity.**  
Explanation: Health checks exist, structured logs exist, `/v1*` is now closed by a WebUI-managed API key, but there is still a way to go to a full production-ready environment: metrics export is not completed, WebUI/backend is not fully separated, and some external integrations are fragile by nature.

Final project score: **80/100**.

## Update: WebUI-First Security

**Thesis: The decision to manage the proxy key via WebUI aligns with the project's product philosophy.**  
Explanation: ChironAI is developing as a local platform, not a set of CLI scripts. Therefore, key generation, disclosure, rotation, and deletion should live in the WebUI. Env/YAML remain bootstrap/recovery layers but not the primary interface for daily work.

**Thesis: Protection has actually increased, but the model is intentionally more convenient than GitHub-style show-once.**  
Explanation: `/v1*` is no longer accidentally open when binding to a network: a Chiron API key is required. At the same time, the key is recoverable because the same secret is used in several IDEs, OpenWebUI provider settings, and external OpenAI-compatible clients. This is a compromise: weaker than a non-recoverable token, but better suited for a local WebUI-first system.

**Thesis: The current trust boundary must be clearly kept in mind.**  
Explanation: Chiron OpenAI/Anthropic-compatible `/v1*` endpoints are protected. Ollama passthrough `/api/tags`, `/api/show`, `/api/generate`, `/api/chat` are intentionally left without a Chiron key to avoid breaking OpenWebUI/Ollama-style backends. This is not a bug but a compatibility decision, but it should be shown in the UI and documentation.

## What's in the Project

| Area | Score | What's there | Explanation |
|---|---:|---|---|
| Architecture | 82 | Hexagonal/layered split, CoreModules, contracts | Layers are readable, domain ports exist, but migration is not complete. |
| RAG pipeline | 86 | query prep, dense/sparse search, rerank, coverage, context assembly | Functionally, this is above average for a local RAG system. |
| LLM Proxy | 83 | `/v1/chat/completions`, `/v1/messages`, `/v1/completions`, tools, vision, builds | Rich surface area, but the handler file is too large. |
| Ingestion | 78 | filtering, normalization, chunking, md_indexer, retries | Good foundation; stricter index quality reporting is needed. |
| WebUI | 76 | React/Vite SPA, dashboard, logs, RAG settings, tests UI, proxy key management | Functionally rich and better covers admin scenarios, but components are sometimes overloaded. |
| Tests | 89 | 492 green tests + CoreUI build | Excellent indicator; missing CI-quality LLM/RAG answers as a stable baseline. |
| Observability | 72 | proxy traces, request logs, timing fields, health endpoints | Already useful, but one step away from production observability. |
| Security | 73 | WebUI-managed key for `/v1*`, path safety in apply-edit, SSRF flags off by default | Significantly better: direct access to Chiron `/v1*` is now fail-closed. Risk remains in recoverable secret and open `/api/*` compatibility path. |
| DX / Launch | 68 | docs, scripts, editable modules | Many entry points and `PYTHONPATH` logic complicate onboarding. |
| Documentation | 76 | README, architecture docs, module docs, TODO/Improvement | Many documents, but some texts were damaged by encoding. |

## Architecture

**Thesis: The target architecture is good: Presentation -> Application -> Domain -> Infrastructure.**  
Explanation: `docs/ARCHITECTURE.md`, `docs/MODULAR_STRUCTURE.md`, `domain/ports/*`, `CoreModules/RagService`, `CoreModules/MdIngestionService`, `CoreModules/LlmProxy` show the right direction.

**Thesis: The project is currently in a hybrid state between a monolith and a modular platform.**  
Explanation: `api/http/webui_routes.py` contains 4247 lines, `CoreModules/LlmProxy/llm_proxy/chat_completions.py` - 4118 lines. This is not a disaster, but these are clear centers of risk.

**Thesis: Module boundaries are already conceptualized but not always brought to physical isolation.**  
Explanation: `modules/webui_backend` exists as a target backend, but the main WebUI API still lives in legacy Flask routes.

**Thesis: The import-linter contract for domain is the right decision.**  
Explanation: `pyproject.toml` prohibits `domain -> application/api/infrastructure`, which protects the inner layer from dependency sprawl.

## RAG Pipeline

**Thesis: The RAG pipeline is the strongest part of the project.**  
Explanation: The pipeline is divided into `query_prep`, `embed_search_pass1`, `concept_expansion_pass2`, `metadata_rank`, `rerank`, `coverage_gate`, `coverage_supplemental`, `context_assembly`.

**Thesis: Hybrid search is enabled by default, and that's correct.**  
Explanation: Dense embeddings catch meaning well, sparse signal catches exact API/symbol terms. For Swift/iOS documentation, this is critical because `NavigationStack`, `@Observable`, `UIViewController` cannot be reliably searched only semantically.

**Thesis: Coverage gate is a strong idea, but some advanced flags are currently disabled.**  
Explanation: `coverage_aware_selection`, `coverage_gate_enabled`, `coverage_retry_supplemental_search_enabled`, `query_expansion_enabled`, `concept_expansion_enabled` in `config/retrieval.yaml` are false by default. This reduces latency risk but leaves quality not at its maximum.

**Thesis: Rerank is implemented practically, but the default model is conservative.**  
Explanation: Fallback `bbjson/bge-reranker-base` is light and fast, but for complex code/docs queries, it's better to have a profile on `bge-reranker-v2-m3`.

**Thesis: RAG tests are a big plus.**  
Explanation: `rag_tests/*` describes questions, expected concepts, strict RAG overlap. This is the correct form of regression for RAG because unit tests don't catch retrieval quality degradation.

## LLM Proxy

**Thesis: LLM Proxy is functionally powerful.**  
Explanation: Supports OpenAI chat, legacy completions, Anthropic Messages, Ollama passthrough, build presets, tool calls, vision data URLs, external docs ingest, apply-edit.

**Thesis: The OpenAI-compatible layer is overloaded with responsibilities.**  
Explanation: `chat_completions.py` does routing, RAG, web supplement, tool mediation, streaming, Gemini compatibility, logs, token estimates, budget compaction, and response shaping. This is a lot for one file.

**Thesis: The single-chunk SSE workaround is honestly documented and necessary.**  
Explanation: `known_bugs.md` correctly separates transport problem and model/tool behavior problem. This is a mature approach: not hiding the limitation but explicitly providing a switch.
