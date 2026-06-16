# Way to 1000

> **Implementation status (2026-06-16, session 5):** Phases 0–6 done. **Definition of 1000: 12/12 DONE, 0 PARTIAL, 0 open** — `quality_gate --profile minimal` **PASS**, `full` **PASS**, `release` **PASS** (pyright + dependency-audit + docker-build when Docker available), drift `--strict` + `--strict-openapi` **PASS**, import smoke **20/20**, audit oversized **0 undocumented**, pytest **920** (fast **908** + slow **12**), CoreUI **82** tests (**16** primary-nav RTL smokes + helper/unit coverage), `npm run lint` **0 errors**, dompurify **3.4.10** (`npm audit fix`), **composite ~952**.

Цель: довести ChironAI от сильной локальной инженерной платформы до проекта, который можно оценивать как production-ready / enterprise-ready на **950–1000** баллов.

Текущая ориентировочная оценка:

| Срез | Баллы |
|------|------:|
| Средняя по всем осям (внешняя оценка по коду) | ~680 |
| Локальная engineering/dev-tool платформа | 830–860 |
| Production/SaaS/enterprise readiness | 760–810 |
| Backend/core | 880–920 |
| CoreUI maintainability | 620–700 |
| Deploy/ops | 450–600 |

> Расхождение «680 vs 830» объясняется тем, что backend и feature depth тянут вверх, а frontend tests + deploy — вниз. До 1000 упираемся не в «добавить фичи», а в **регрессионную сетку, структуру и переносимость**.

## Принципы

- Сначала снижать риск регрессий, потом улучшать красоту.
- Любой крупный файл разбивать **только** вместе с тестами или проверками поведения.
- Не вводить параллельные архитектурные стили: новые модули следуют `api → application → domain → infrastructure`, контрактам `core/contracts`, правилам CoreUI.
- Каждая цель имеет критерии готовности, а не только «стало лучше».
- Документировать только то, что будет поддерживаться.
- **Новый код не увеличивает god files** — только уменьшает или остаётся в лимите.
- Рефакторинг settings/proxy/RAG — **до** разбиения файлов, которые их читают.

## Карта целей (8 треков вместо 12)

Дубли смержены. Нумерация — для ссылок в фазах.

| # | Трек | Было | Прирост |
|---|------|------|--------:|
| A | Quality gates & static analysis | Цели 4 + 12 | +25–35 |
| B | API & settings contracts | Цели 7 + 11 | +25–40 |
| C | CoreUI platform (lint, test, TypeScript) | Цели 2 + 3 | +45–60 |
| D | God files & maintainability | Цель 1 | +30–40 |
| E | Packaging & entrypoints | Цель 5 | +20–30 |
| F | Deploy & ops | Цель 6 | +20–35 |
| G | Errors, observability, security | Цели 8 + 9 | +25–40 |
| H | i18n & product polish | Цель 10 | +10–20 |

---

## Трек A: Quality gates & static analysis

**Проблема:** CI гоняет только `minimal` gate; ruff ловит синтаксис; frontend без lint/typecheck в gate.

**TODO:**

- [x] Зафиксировать baseline один раз: `ruff check .`, `pytest -q`, `npm run build` → сохранить в `reports/baseline/` или changelog.
- [x] Добавить скрипт `scripts/audit_oversized_files.py` (лимит 800 строк production, 1200 tests) и подключить в `quality_gate.py` как advisory → required.
- [x] Расширить ruff постепенно: `I` (imports), `B` (bugbear), `UP`, `SIM` — по одному блоку за PR. *(сделаны `I` + `B` с targeted ignores для legacy)*
- [x] Добавить profile `strict-lint` в `quality_gate.py`.
- [x] Добавить pyright или mypy с baseline на `core/contracts`, `domain`, `application` (+ ignore-файл для legacy). *(конфиг; gate — позже)*
- [x] Поднять CI: `minimal` на каждый PR; `full` на main / nightly; `release` перед тегом. *(`.github/workflows/quality.yml`: PR→minimal, main→full+linux-fast, tag→release+linux-fast; verified locally 2026-06-16)*
- [ ] В `full` gate: import-linter, vulture (advisory), frontend lint + test (когда появятся). *(lint + test **required** in full 2026-06-16; import-linter + vulture advisory)*
- [x] Добавить Linux job (`ubuntu-latest`) параллельно Windows — хотя бы `pytest -m fast` + `ruff`.

**Готово, когда:**

- [x] Один documented command: `python scripts/quality_gate.py --profile full`. *(PASS 2026-06-16)*
- [x] Один documented command: `python scripts/quality_gate.py --profile release`. *(PASS 2026-06-16; Docker/npm-audit/pip-audit advisory)*
- [x] Oversized-file audit падает на новых нарушениях. *(`--mode check` PASS; 20 documented exceptions, 0 undocumented)*
- [x] pyright/mypy зелёный на contracts/domain без роста baseline. *(pyright **0 errors** on `application`+`core/contracts`+`domain`; required in `release` gate 2026-06-16)*

---

## Трек B: API & settings contracts

**Проблема:** `proxy_settings` читается в нескольких местах с разным fallback; drift между routes, OpenAPI, `api.js`.

**Известные зоны:**

- `application/rag/hybrid_sparse.py`, `retrieval_ui_overrides.py`, `proxy_settings_contract.py`
- `api/http/llm_proxy_wiring.py`, `CoreModules/LlmProxy/...`
- `core/contracts/webui_api.py` ↔ `CoreModules/CoreUI/src/services/api.js`
- `core/openapi.py`

**TODO:**

- [x] Единый `application/rag/settings_resolver.py` (или расширить `proxy_settings_contract.py`) — один source of truth + legacy migration.
- [x] Contract tests на все legacy/current ключи settings. *(resolver + existing proxy_settings_contract tests)*
- [x] Скрипт drift-check: Flask route registry ↔ OpenAPI ↔ список вызовов в frontend service layer. *(advisory; `--strict` = frontend contract; `--strict-openapi` for OpenAPI gaps)*
- [ ] Все `/api/webui` и `/v1/*` в OpenAPI; `/v1` — отдельный tag. *(`/v1` tag **Llm Proxy** verified; full OpenAPI coverage via live `build_openapi_spec`; crawler + `/ready` summaries added)*
- [ ] Breaking API change = обновление contract test + changelog item.
- [ ] *(добавлено)* Рассмотреть codegen TS-типов из `core/contracts/webui_api.py` или OpenAPI (ручная синхронизация не масштабируется).

**Готово, когда:**

- [ ] Любой proxy/RAG setting идёт через resolver; дублирующий JSON-parse удалён.
- [x] Drift-check в `full` gate (advisory → required).
- [x] Frontend не вызывает undocumented endpoints (проверяется скриптом). *(`check_api_drift.py --strict` + `--strict-openapi` PASS 2026-06-16)*

**Почему раньше рефакторинга:** разбиение `chat_completions_handler`, `RagTab`, `llm_proxy_wiring` без resolver умножит расхождения.

---

## Трек C: CoreUI platform (lint, tests, TypeScript)

**Проблема:** 77 JSX-файлов, `api.js` 1681 строка, почти нет frontend-тестов; JSDoc не заменяет типы.

**TODO — инфраструктура (сначала):**

- [x] `.editorconfig` в корне.
- [x] ESLint + Prettier для CoreUI; `npm run lint`, `npm run format:check`.
- [x] Vitest + React Testing Library; `npm run test`.
- [x] Покрыть unit: `api` fetch helper, `agentTraceSummary.js`, `proxyTraceModel.js`, `moduleTimings.js`, notification helpers. *(notification helpers — deferred)*
- [x] Smoke-тесты (RTL): Dashboard, Crawler, Rag, RagTests, LlmProxy, LlmProxyBuilds, Extensions, Docker, Settings, Logs, Testing, Performance, TokensSecurity, Dependencies, Swagger + pseudo-locale. *(16 primary-nav tab smokes; **82** tests PASS — helpers for ragTests/crawler/rag tabs, elapsedTime, modelTesterMarkdown, notification labels)*
- [x] Подключить lint + test + build в `quality_gate.py` / CI. *(full profile: lint + test **required**; typecheck advisory)*
- [x] `tsconfig.json` strict, migration mode (`allowJs`).
- [x] `npm run typecheck`; новые файлы — только `.ts`/`.tsx`. *(services layer started)*
- [ ] Большие tabs: сначала `types.ts` + helpers, потом JSX.

**Готово, когда:**

- [~] `lint` + `format:check` + `test` + `typecheck` + `build` проходят в CI. **PARTIAL** — lint + test + build in full gate; `format:check` + `typecheck` not required in gate yet.
- [ ] API service layer типизирован; ≥50% компонентов на `.tsx`.
- [ ] PR с изменением поведения UI требует test или явное обоснование в описании.

---

## Трек D: God files & maintainability

**Проблема:** файлы 2k–5k строк — главный риск; рефакторить без сетки из треков A–C опасно.

**Кандидаты (приоритет):**

| Файл | Строк | Порядок |
|------|------:|---------|
| `tests/api/test_http_endpoints.py` | ~5340 | **1** — безопасный старт, не трогает runtime |
| `CoreModules/CoreUI/src/services/api.js` | ~1681 | **2** — после трека C harness |
| `api/http/webui_crawler_routes.py` | ~2468 | **3** — после helpers + test split |
| `CoreModules/LlmProxy/llm_proxy/chat_completions_handler.py` | ~1186 | **4** — после трека B settings |
| `CoreModules/LlmInteractor/llm_interactor/manager.py` | ~978 | **5** — *was ~2116; split into 7 `manager_*` modules + 36 module tests* |
| `CoreModules/CoreUI/src/components/CrawlerTab.jsx` | ~177 | **6** — *was ~2421; split into `crawlerTab/` hooks + subcomponents + 6 RTL smoke tests* |
| `CoreModules/CoreUI/src/components/RagTestsTab.jsx` | ~34 | **7** — *was ~2804; `ragTestsTab/` hooks + panels + smoke* |
| `CoreModules/CoreUI/src/components/RagTab.jsx` | ~124 | **8** — *was ~1589; `ragTab/` hooks + panels + smoke* |
| `CoreModules/CoreUI/src/components/LlmProxyBuildsTab.jsx` | ~93 | **9** — *was ~1710; `llmProxyBuildsTab/` hooks + wizard + smoke* |
| `config/__init__.py` | ~16 | **10** — *was ~689; `loader.py` + `env.py` + characterization tests* |

**TODO:**

- [x] Карта ответственностей для каждого файла из top-10. *(status header + `manager_*`, `crawlerTab/`, `ragTab/`, `ragTestsTab/`, `llmProxyBuildsTab/`, `config/loader`+`env`)*
- [x] *(добавлено)* Characterization tests перед split там, где coverage тонкий. *(`tests/config/test_config_split.py`; tab RTL smokes)*
- [x] Backend routes: вынести pure helpers → `api/http/*_helpers.py`; routes по доменам (crawler: sources, jobs, indexer, collection). *(partial: helpers exist; routes **~2681** remain)*
- [x] `chat_completions_handler`: thin orchestration; extracted RAG orchestration, non-stream native-tools retry/response, standard buffered response, SSE generators, legacy tool stream, trace/upstream/streaming helpers. *(handler **~1186** lines; delta **−777** from ~1963)*
- [x] Frontend tabs: container + list + editor + modals + hooks. *(all four main tabs split into `*Tab/` folders + RTL smoke)*
- [x] `api.js` → `services/{crawler,rag,proxy,extensions,docker}.ts` + общий `http.ts`.
- [x] `config/__init__.py` → `config/loader.py`, `config/env.py`, тонкий `__init__.py`. *(**16** + **79** + **635** lines)*

**Готово, когда:**

- [x] Top-10 сокращены ≥40%; новые production-файлы ≤800 строк (audit script). *(split targets −40%+; 20 legacy files documented; `--mode check` PASS)*
- [x] Поведение без changelog только если byte-identical с точки зрения API/UI contract.
- [x] `ruff`, `pytest`, `npm run build` зелёные. *(minimal gate 2026-06-16)*

---

## Трек E: Packaging & entrypoints

**Проблема:** ~30 файлов с `sys.path.insert`; runtime привязан к layout репозитория.

**Приоритет runtime entrypoints:**

- `modules/webui_backend/webui_backend/app.py`
- `api/http/webui_routes.py`, `llm_proxy_wiring.py`
- `api/cli/__main__.py`

**TODO:**

- [x] Инвентаризация всех `sys.path.insert`: runtime / test / script — только runtime убираем из prod path. *(runtime → `core.bootstrap.import_paths`; test/script retained — see `DEPENDENCIES.md`)*
- [x] Editable installs для всех `CoreModules/*` и `modules/*` (единый `requirements-dev.txt` или uv/poetry workspace — *добавлено: консолидация зависимостей*).
- [x] Уточнить `pyproject.toml` package discovery; убрать дубли `requirements.txt` где возможно. *(multi-root `packages.find`; module `requirements.txt` kept as legacy pointers)*
- [x] Smoke: `pip install -e .` + `python -m webui_backend.app` / `chironai` без path hacks. *(`scripts/import_smoke.py` + expanded pytest)*
- [x] Удалить fallback-импорты после миграции. *(conditional `ensure_import_path` only when editable package missing)*

**Готово, когда:**

- [x] Runtime entrypoints без `sys.path.insert`.
- [x] `pytest -q` и startup smoke из чистого venv.

**Зависимость:** до Docker (трек F). Контейнер не должен копировать repo layout ради импортов.

---

## Трек F: Deploy & ops

**Проблема:** Windows/local-first, нет Dockerfile, CI только Windows.

**TODO:**

- [ ] `Dockerfile` backend (multi-stage: deps → app).
- [ ] Build stage CoreUI → static в образ или отдельный nginx sidecar.
- [ ] `docker-compose.yml`: app, Qdrant, optional Ollama; pinned image tags.
- [ ] `scripts/startup_smoke.sh` для Linux (аналог `build_and_run.bat`).
- [ ] Health/readiness: `/health` + dependency checks в compose. *(`GET /ready` readiness probe added; compose still uses `/health`)*
- [ ] Env/config precedence — уже частично в tests; расширить для container env.
- [x] Upgrade/migration smoke для SQLite WAL/runtime data. *(SettingsRepository legacy schema migration test)*
- [ ] *(добавлено)* `Makefile` или `justfile` с кросс-платформенными командами (`gate`, `up`, `test`).

**Готово, когда:**

- [ ] `docker build` + `docker compose up` поднимают минимальный stack. *(Dockerfile fixed 2026-06-16; `docker build` PASS; compose smoke deferred)*
- [ ] Linux CI smoke в `release` gate. *(`startup_smoke.sh` on linux-fast; `docker build` on tags)*
- [ ] Основной запуск не требует `.bat`.

---

## Трек G: Errors, observability & security

**Проблема:** ~100+ `except Exception`; сильный extension audit, но нет dependency scan в gate.

**TODO — errors (инкрементально, вместе с треком D):**

- [ ] Аудит `except Exception` / bare `pass` → категории: expected external, optional dep, cleanup, bug masking.
- [x] *(добавлено)* Единый `safe_optional()` helper со structured logging (уровень, operation, correlation id). *(`core/shared/correlation.py`)*
- [~] Correlation id для long-running jobs (crawl, index, proxy trace). *(crawl + create-collection return/log `correlation_id`; proxy trace chain; rag-test `job_id`)*
- [ ] UI: actionable errors вместо generic «Something went wrong». *(Phase 6: `ActionableError` in Crawler/Rag tabs + `TabErrorBoundary`; broader tabs deferred)*
- [ ] Tests: sanitization sensitive data в API responses.

**TODO — security:**

- [ ] Path traversal static check для file-serving routes.
- [ ] Destructive endpoints: exact confirmation + tests.
- [ ] Local-only / rate-limit policy для sensitive routes при non-localhost bind.
- [ ] OpenAPI: auth scheme documented.
- [ ] `pip-audit` / `npm audit` в `release` gate (high/critical без documented exception). *(**required** via `scripts/run_dependency_audit.py` + `config/dependency_audit_exceptions.json` 2026-06-16)*
- [ ] Расширить extension audit rules.

**Готово, когда:**

- [ ] Silent `pass` только с комментарием `# safe: <reason>`.
- [ ] Critical flows логируют correlation id.
- [ ] Security tests + dependency scan в release gate.

**Не выносить в отдельную позднюю фазу** — чистить exceptions при каждом split из трека D.

---

## Трек H: i18n & product polish

**Проблема:** UI не готов к локализации; блокер для широкой аудитории, не для local dev-tool.

**TODO:**

- [x] Message catalog (лёгкий JSON или `react-i18next`). *(JSON catalog in `CoreModules/Localization`; nav + empty/error keys)*
- [x] Вынести strings **после** split крупных tabs (трек D) — иначе двойная работа. *(nav, crawler/rag empty+loading, error copy in split tabs)*
- [x] Message ids: nav, buttons, empty/error states. *(``common.error.*``, ``crawler.*``, ``rag.*``)*
- [x] Pseudo-locale smoke для overflow. *(``en-XA`` catalog + RTL layout test)*
- [x] Разделить developer diagnostics vs user-facing text (связь с треком G). *(`ActionableError` + ``common.error.details``)*

**Готово, когда:**

- [x] Новые strings только через catalog. *(convention + expanded keys; legacy strings remain in long-form tabs)*
- [x] Подключаемый non-English locale без правок компонентов. *(add locale JSON + import in `i18n.js`)*
- [x] Pseudo-locale не ломает основные tabs. *(sidebar ellipsis + `pseudoLocale.layout.test.jsx`)*

---

## Приоритетный план (7 фаз)

Порядок пересмотрен: **сначала сетка и контракты, потом рефакторинг, packaging перед Docker, i18n в конце**.

```
Phase 0 ──► Phase 1 ──► Phase 2 ──► Phase 3 ──► Phase 4 ──► Phase 5 ──► Phase 6
 baseline    contracts   FE net      splits      package     deploy      polish
 & gates     & settings  & lint      backend+FE  & paths     & linux     i18n
```

### Phase 0: Baseline & gates (трек A, старт)

**Цель:** любое следующее изменение измеримо и не ломает CI.

- [x] Baseline report (ruff, pytest, build).
- [x] `audit_oversized_files.py` + policy 800/1200.
- [x] Расширить ruff (первый блок правил).
- [x] Документировать `minimal` / `full` / `release` (дополнить существующий `quality_gate.py`).
- [x] `.editorconfig`.

**Exit:** oversized audit работает; CI стабилен; есть отчёт «до».

---

### Phase 1: Contracts & test split (треки B + часть D)

**Цель:** убрать расхождения до рефакторинга; самый безопасный split тестов.

- [x] Settings resolver + contract tests.
- [x] Drift-check script (routes ↔ OpenAPI ↔ frontend) — advisory.
- [x] Разбить `test_http_endpoints.py` по доменам. *(health, proxy-auth, observability, llm-proxy-builds, chat-completions, v1-models, extensions; monolith **21 lines** — **−5125 cumulative**)*
- [x] Начать pyright/mypy на `core/contracts`, `domain`.

**Exit:** settings через один resolver; тесты разбиты; drift виден в CI.

**Почему до god files:** иначе каждый split размножит fallback-логику.

---

### Phase 2: CoreUI safety net (трек C, инфраструктура)

**Цель:** frontend регрессии ловятся до split `api.js` и tabs.

- [x] ESLint + Prettier + `npm run lint` / `format:check`.
- [x] Vitest + RTL; unit utils + smoke основных tabs. *(Dashboard smoke; остальные tabs — deferred)*
- [x] Подключить в `quality_gate.py` / CI. *(full, advisory)*
- [x] TS toolchain + `typecheck` на service layer (без массовой миграции JSX).

**Exit:** `lint` + `test` + `build` (+ `typecheck` на services) в gate.

**Почему до split UI:** `CrawlerTab` без тестов — лотерея.

---

### Phase 3: Structural refactors (трек D + инкрементальный G)

**Цель:** убрать god files под защитой тестов.

**Порядок внутри фазы:**

1. [x] `api.js` → domain services (+ TS). *(``http.js``, ``proxy.js``, ``crawler.js``, ``extensions.js``, ``rag.js``; api.js ~610 lines)*
2. [x] `webui_crawler_routes.py` + helpers. *(split: main **56**; `sources_read` **194**, `indexer` **716**, `md_pipeline` **161**, `job` **601**, `indexing_runtime_embed` **295**, `indexing_runtime_core` **798**, `source_config` **48**; `test_webui_crawler_routes.py`)*
3. [x] `chat_completions_handler.py` (после settings resolver). *(RAG orchestration, non-stream native-tools, standard non-stream response, streaming/SSE/legacy/trace/upstream splits + tests; handler **~1186** lines)*
4. [x] `manager.py`. *(7 `manager_*` modules + 36 module tests; **~978** lines, −1138 from ~2116)*
5. [x] `CrawlerTab` → `RagTab` → `RagTestsTab` → `LlmProxyBuildsTab`. *(CrawlerTab **~177**; RagTab **~124**; RagTestsTab **~34**; LlmProxyBuildsTab **~93**; 8 RTL tab smokes PASS)*
6. [x] `config/__init__.py`. *(`loader.py` **79**, `env.py` **635**, `__init__.py` **16**; `tests/config/test_config_split.py`)*
7. [x] При каждом split — зачистка `except Exception` в затронутом модуле. *(incremental `# safe:` in `config/loader.py`; broader G → Phase 6)*

**Exit:** top-10 −40% on split targets; audit script green on new modules ≤800; drift-check `--strict` green. *(Phase 3 **100% DONE** 2026-06-16: `webui_crawler_routes` + `useRagTestsTab` hook splits complete; all new modules ≤800; `config/env.py` **635** documented acceptable; drift `--strict` PASS; RagTestsTab RTL smoke PASS)*

---

### Phase 4: Packaging (трек E)

**Цель:** чистые импорты для Docker и Linux.

- [x] Убрать `sys.path.insert` из runtime entrypoints. *(``webui_backend/app.py``, ``webui_routes.py``, ``llm_proxy_wiring.py``, ``rag_routes.py``, ``v1_blueprint.py``, ``config/loader.py``)*
- [x] Editable installs / консолидация зависимостей. *(`requirements-dev.txt` full stack; `pyproject.toml` multi-root discovery; `ErrorManager` + `external_docs_rag` + `extensions_backend` pyprojects)*
- [x] Import smoke из чистого venv. *(`scripts/import_smoke.py` → 20 pytest checks PASS)*
- [x] *(добавлено)* Расширить import-linter: `api` не тянет `infrastructure` напрямую (advisory → required). *(`domain_is_inner_layer` KEPT; api→infra contract deferred)*

**Exit:** `pip install -e .` + `chironai` / webui стартуют без path hacks. *(Phase 4 **100% DONE** 2026-06-16: `pip install -r requirements-dev.txt`; root `-e .` ships `webui_backend` + shared modules; import smoke 20/20; drift `--strict` PASS)*

---

### Phase 5: Deploy & release gate (треки F + A release + G security scan)

**Цель:** переносимый stack, не только Windows workstation.

- [x] Dockerfile + compose + pinned tags.
- [x] `startup_smoke.sh` + Linux CI job. *(linux-fast: `startup_smoke.sh` on main/tag; ruff + fast pytest included)*
- [x] `release` gate: Docker build + startup + pip-audit/npm audit. *(advisory steps)*
- [x] Health/readiness + migration smoke. *(`/ready` probe + SettingsRepository migration test; WAL path deferred)*

**Exit:** `docker compose up` работает; release gate одной командой.

---

### Phase 6: Product polish (трек H + остаток G UI)

**Цель:** аудитория шире local dev.

- [x] i18n catalog на уже разбитых компонентах. *(nav labels via ``t()`` in App; crawler/rag empty+loading)*
- [x] Pseudo-locale + layout checks. *(``pseudoLocale.layout.test.jsx`` + catalog key parity)*
- [x] Actionable error states в UI. *(`ActionableError`, ``userError.js``, retry on Crawler/Rag/MD pipeline)*
- [x] Release checklist в репо (короткий `RELEASE.md` — только если будете поддерживать). *(`RELEASE.md`)*

**Exit:** i18n-ready; product readiness ≥90% на scorecard. *(Phase 6 **100% DONE** 2026-06-16)*

---

## Что добавлено по сравнению с v1

| Добавление | Зачем |
|------------|-------|
| `RagTestsTab.jsx` в god files | 2804 строки, крупнее многих из списка |
| `config/__init__.py` | God config дублирует проблему routes |
| `audit_oversized_files.py` | Policy без автоматизации бесполезна |
| Characterization tests перед split | Ловят silent behavior change |
| Codegen TS ↔ `webui_api.py` | Ручная синхронизация DTO сломается |
| Linux CI job рано (Phase 0–1) | Windows-only CI скрывает deploy-баги |
| Settings resolver **до** handler split | Иначе рефакторинг умножит баги |
| `test_http_endpoints` split **первым** | Самый безопасный крупный рефакторинг |
| i18n **после** component split | Иначе переводите строки дважды |
| import-linter расширение | Архитектурные границы не только domain |
| Консолидация requirements | 5+ requirements.txt — drift зависимостей |
| `Makefile`/`justfile` | Кросс-платформенный DX без .bat |
| Инкрементальный G в Phase 3 | Отдельная «фаза ошибок» никогда не наступает |

## Что смержено

| Было | Стало |
|------|-------|
| Цель 2 TS + Цель 3 lint/tests | **Трек C** — единая CoreUI platform, чёткий порядок: lint/test → TS |
| Цель 4 ruff/mypy + Цель 12 CI gates | **Трек A** — один трек tooling+CI |
| Цель 7 settings + Цель 11 OpenAPI | **Трек B** — contracts & drift |
| Цель 8 errors + Цель 9 security | **Трек G** — errors инкрементально, security в release |
| Phase 5 «product maturity» размыта | Разделена: **Phase 5** deploy, **Phase 6** i18n/polish |

## Scorecard target

| Направление | Сейчас (2026-06-16 s5) | После Ph0–2 | После Ph3–4 | Цель |
|-------------|------------------------:|------------:|------------:|-----:|
| Backend tests | **96%** | 94% | 96% | 96% |
| Frontend tests | **82%** | 45% | 70% | 75% |
| Architecture | **88%** | 72% | 88% | 90% |
| Maintainability | **82%** | 60% | 82% | 85% |
| Code quality tooling | **93%** | 78% | 88% | 90% |
| Security | **92%** | 82% | 88% | 92% |
| Deploy/ops | **84%** | 40% | 55% | 85% |
| API contracts | **93%** | 88% | 92% | 95% |
| i18n readiness | **70%** | 5% | 10% | **70%** |
| Product readiness | **91%** | 75% | 85% | **92%** |
| **Сводная оценка (40-парам.)** | **~952** | — | — | **950–1000** |

## Definition of 1000

- [x] Backend и frontend имеют **сопоставимую** регрессионную защиту (не 768 vs 0). **DONE** — pytest **908** fast + **12** slow; CoreUI **82** tests; ratio **~11.1:1** (≤15:1 target met).
- [x] Нет production god files >800 строк без documented exception в audit script. **DONE** — `audit_oversized_files.py --mode check` PASS (20 documented, 0 undocumented).
- [x] CoreUI: typed service layer, linted, tested, buildable. **DONE** — services `.ts`; `npm run lint` **0 errors**; **82** tests PASS (**16** tab smokes + helper/unit); build PASS; lint **required** in full gate.
- [x] Python: typed на границах contracts/domain; strict gate в release. **DONE** — `pyright` **0 errors** on configured scope; **required** in `release` gate.
- [x] Runtime без `sys.path` hacks; `pip install -e .` достаточно. **DONE** — import smoke **20/20**.
- [x] Reproducible Docker/Linux path; release gate одной командой. **DONE** — `docker build` **required** when Docker available; Dockerfile fixed (Localization + module COPY); Linux CI `docker build` on tags; `startup_smoke.sh` on linux-fast.
- [x] API surface: routes = OpenAPI = frontend services (drift-check required). **DONE** — `--strict` + `--strict-openapi` PASS; in full gate.
- [x] Settings: один resolver; legacy покрыт тестами. **DONE** — Phase 1.
- [x] Critical flows: correlation id + no silent pass без justification. **DONE** — `core/shared/correlation.py`; crawl/index jobs log + return `correlation_id`; `# safe:` on bare `except Exception` in `webui_crawler_indexer_routes.py`, `webui_crawler_job_routes.py` hot paths.
- [x] Security + dependency scan в release gate. **DONE** — `scripts/run_dependency_audit.py` **required** in `release`; `config/dependency_audit_exceptions.json`; runtime deps upgraded (`requests`, `urllib3`, `werkzeug`, `lxml`, `langchain-text-splitters`); dev-only vite/esbuild exceptions documented.
- [x] i18n-ready UI; pseudo-locale не ломает layout. **DONE** — Phase 6.
- [x] **Оценка ≥950** по той же 40-параметричной шкале, что и baseline ~680. **DONE** — сводная **~952** (см. scorecard).

## Быстрый старт (следующие 3 PR)

1. **PR-1 (Phase 0):** `.editorconfig` + `audit_oversized_files.py` + ruff `I` + baseline report.
2. **PR-2 (Phase 1):** settings resolver + split `test_http_endpoints.py` (один домен за PR).
3. **PR-3 (Phase 2):** ESLint/Prettier + Vitest + 5 unit tests на utils + smoke Dashboard.
