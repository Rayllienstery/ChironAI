# ChironAI v0.4

## First of the first
- [ ] Xcode example

## Quick Notes (from Notes)

- [ ] Auto start docker
- [ ] Esp 32 integration
- [ ] Live session fix ui
- [ ] Unificate right bottom menu
- [ ] iPhone notifications
- [ ] Web framework search - work the same as crawl...

- [ ] Check RAG Quality TASK
- [ ] Crawler / Indexer - improve understanding of what was indexed and what was not - Indexed is ok, but skipped count is mandatory
- [ ] Indexing debug - why so much <400 chars filtering, probably it is useful files
- [ ] Indexing debug - Embedding failed: 3

## Bugs

## 1. RAG (retrieval)

### 1.2 Chunking and context
- [ ] **A/B tests of context limits** — quality comparison for different models and context sizes after fixing base limits.

### 1.4 Concept Coverage (new priority layer)

---

## 2. Prompt

### 2.1 Content
- [ ] **A/B tests** — ability to pass a prompt variant via query param or header (e.g., `X-Prompt-Variant: short`) for quality comparison without deployment.

## 4. Models and embeddings

---

## 5. Testing and quality assessment

### 5.1 Regression tests
- [x] **Reference set in JSON/YAML** — implemented via Markdown tests in `rag_tests/` and result storage in SQLite.
- [x] **Integration with app_tester** — implemented via `rag_tests_routes.py` and `runner.py`.

### 5.2 Benchmarks
- [x] **Latency** — `latency_ms` is logged, displayed in UI (p50/p95).
- [x] **Retrieval quality** — implemented in RAG tests (Hit@K, MRR).
- [x] **Answer quality** — concept validation implemented in `validator.py`.

---

## 6. Observability and operations

- [ ] **Metrics export** — export to Prometheus/StatsD or a separate `GET /metrics` (currently only in-memory collector).
- [ ] **Health: probe `/api/embed`** — add embedding check (see checklist in `Improvement.md` §6.1).

---

## 7. Documentation and project structure

- [ ] **Prompt description** — separate document (e.g., `docs/PROMPT.md`).

---

## 8. Code quality (project)

- [ ] **Typing** — enable type checking (mypy or pyright) for `rag_proxy.py`, key functions in `app.py`.
- [x] **Russian comments** — translate to English for uniformity.

---

## Priorities v0.4 (Quality and Operations)

1. **Observability:** [ ] Export metrics to Prometheus (`/metrics`), [ ] Health probe for `/api/embed`.
2. **RAG:** [ ] Improve indexer reporting (skipped count), [ ] Debug filtering of short files (<400 chars).
3. **Prompt:** [ ] A/B test mechanism for prompts via headers.
4. **Documentation:** [ ] Create CHANGELOG.md, [ ] Describe prompt architecture.

---

## Post MVP
Tasks moved to **[POST_MVP.md](POST_MVP.md)**.
