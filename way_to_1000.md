# Way to 1000

> **Implementation status (2026-06-15):** Phases 0–2 largely done; Phase 3–4 in progress. Full checklist, gate results, and score estimate: [`reports/WAY_TO_1000_SNAPSHOT.md`](reports/WAY_TO_1000_SNAPSHOT.md).

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
- [ ] Поднять CI: `minimal` на каждый PR; `full` на main / nightly; `release` перед тегом.
- [ ] В `full` gate: import-linter, vulture (advisory), frontend lint + test (когда появятся).
- [x] Добавить Linux job (`ubuntu-latest`) параллельно Windows — хотя бы `pytest -m fast` + `ruff`.

**Готово, когда:**

- [ ] Один documented command: `python scripts/quality_gate.py --profile full`.
- [ ] Один documented command: `python scripts/quality_gate.py --profile release`.
- [ ] Oversized-file audit падает на новых нарушениях.
- [ ] pyright/mypy зелёный на contracts/domain без роста baseline.

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
- [x] Скрипт drift-check: Flask route registry ↔ OpenAPI ↔ список вызовов в frontend service layer. *(advisory)*
- [ ] Все `/api/webui` и `/v1/*` в OpenAPI; `/v1` — отдельный tag.
- [ ] Breaking API change = обновление contract test + changelog item.
- [ ] *(добавлено)* Рассмотреть codegen TS-типов из `core/contracts/webui_api.py` или OpenAPI (ручная синхронизация не масштабируется).

**Готово, когда:**

- [ ] Любой proxy/RAG setting идёт через resolver; дублирующий JSON-parse удалён.
- [x] Drift-check в `full` gate (advisory → required).
- [ ] Frontend не вызывает undocumented endpoints (проверяется скриптом).

**Почему раньше рефакторинга:** разбиение `chat_completions_handler`, `RagTab`, `llm_proxy_wiring` без resolver умножит расхождения.

---

## Трек C: CoreUI platform (lint, tests, TypeScript)

**Проблема:** 77 JSX-файлов, `api.js` 1681 строка, почти нет frontend-тестов; JSDoc не заменяет типы.

**TODO — инфраструктура (сначала):**

- [x] `.editorconfig` в корне.
- [x] ESLint + Prettier для CoreUI; `npm run lint`, `npm run format:check`.
- [x] Vitest + React Testing Library; `npm run test`.
- [x] Покрыть unit: `api` fetch helper, `agentTraceSummary.js`, `proxyTraceModel.js`, `moduleTimings.js`, notification helpers. *(notification helpers — deferred)*
- [x] Smoke-тесты (RTL): Dashboard, Rag, Crawler, LlmProxy, Extensions, Docker — render + loading/error/empty. *(Dashboard + Rag smoke)*
- [x] Подключить lint + test + build в `quality_gate.py` / CI. *(full profile, advisory)*
- [x] `tsconfig.json` strict, migration mode (`allowJs`).
- [x] `npm run typecheck`; новые файлы — только `.ts`/`.tsx`. *(services layer started)*
- [ ] Большие tabs: сначала `types.ts` + helpers, потом JSX.

**Готово, когда:**

- [ ] `lint` + `format:check` + `test` + `typecheck` + `build` проходят в CI.
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
| `CoreModules/LlmProxy/llm_proxy/chat_completions_handler.py` | ~2601 | **4** — после трека B settings |
| `CoreModules/LlmInteractor/llm_interactor/manager.py` | ~2110 | **5** |
| `CoreModules/CoreUI/src/components/CrawlerTab.jsx` | ~2421 | **6** |
| `CoreModules/CoreUI/src/components/RagTestsTab.jsx` | ~2804 | **7** — *добавлен, пропущен в v1* |
| `CoreModules/CoreUI/src/components/RagTab.jsx` | — | **8** |
| `CoreModules/CoreUI/src/components/LlmProxyBuildsTab.jsx` | ~1710 | **9** |
| `config/__init__.py` | ~689 | **10** — *добавлен: god config* |

**TODO:**

- [ ] Карта ответственностей для каждого файла из top-10.
- [ ] *(добавлено)* Characterization tests перед split там, где coverage тонкий.
- [ ] Backend routes: вынести pure helpers → `api/http/*_helpers.py`; routes по доменам (crawler: sources, jobs, indexer, collection).
- [ ] `chat_completions_handler`: orchestration, tools, RAG supplement, upstream, trace persistence.
- [ ] Frontend tabs: container + list + editor + modals + hooks.
- [ ] `api.js` → `services/{crawler,rag,proxy,extensions,docker}.ts` + общий `http.ts`.
- [ ] `config/__init__.py` → `config/loader.py`, `config/env.py`, тонкий `__init__.py`.

**Готово, когда:**

- [ ] Top-10 сокращены ≥40%; новые production-файлы ≤800 строк (audit script).
- [ ] Поведение без changelog только если byte-identical с точки зрения API/UI contract.
- [ ] `ruff`, `pytest`, `npm run build` зелёные.

---

## Трек E: Packaging & entrypoints

**Проблема:** ~30 файлов с `sys.path.insert`; runtime привязан к layout репозитория.

**Приоритет runtime entrypoints:**

- `modules/webui_backend/webui_backend/app.py`
- `api/http/webui_routes.py`, `llm_proxy_wiring.py`
- `api/cli/__main__.py`

**TODO:**

- [ ] Инвентаризация всех `sys.path.insert`: runtime / test / script — только runtime убираем из prod path.
- [ ] Editable installs для всех `CoreModules/*` и `modules/*` (единый `requirements-dev.txt` или uv/poetry workspace — *добавлено: консолидация зависимостей*).
- [ ] Уточнить `pyproject.toml` package discovery; убрать дубли `requirements.txt` где возможно.
- [ ] Smoke: `pip install -e .` + `python -m webui_backend.app` / `chironai` без path hacks.
- [ ] Удалить fallback-импорты после миграции.

**Готово, когда:**

- [ ] Runtime entrypoints без `sys.path.insert`.
- [ ] `pytest -q` и startup smoke из чистого venv.

**Зависимость:** до Docker (трек F). Контейнер не должен копировать repo layout ради импортов.

---

## Трек F: Deploy & ops

**Проблема:** Windows/local-first, нет Dockerfile, CI только Windows.

**TODO:**

- [ ] `Dockerfile` backend (multi-stage: deps → app).
- [ ] Build stage CoreUI → static в образ или отдельный nginx sidecar.
- [ ] `docker-compose.yml`: app, Qdrant, optional Ollama; pinned image tags.
- [ ] `scripts/startup_smoke.sh` для Linux (аналог `build_and_run.bat`).
- [ ] Health/readiness: `/health` + dependency checks в compose.
- [ ] Env/config precedence — уже частично в tests; расширить для container env.
- [ ] Upgrade/migration smoke для SQLite WAL/runtime data.
- [ ] *(добавлено)* `Makefile` или `justfile` с кросс-платформенными командами (`gate`, `up`, `test`).

**Готово, когда:**

- [ ] `docker build` + `docker compose up` поднимают минимальный stack.
- [ ] Linux CI smoke в `release` gate.
- [ ] Основной запуск не требует `.bat`.

---

## Трек G: Errors, observability & security

**Проблема:** ~100+ `except Exception`; сильный extension audit, но нет dependency scan в gate.

**TODO — errors (инкрементально, вместе с треком D):**

- [ ] Аудит `except Exception` / bare `pass` → категории: expected external, optional dep, cleanup, bug masking.
- [ ] *(добавлено)* Единый `safe_optional()` helper со structured logging (уровень, operation, correlation id).
- [ ] Correlation id для long-running jobs (crawl, index, proxy trace).
- [ ] UI: actionable errors вместо generic «Something went wrong».
- [ ] Tests: sanitization sensitive data в API responses.

**TODO — security:**

- [ ] Path traversal static check для file-serving routes.
- [ ] Destructive endpoints: exact confirmation + tests.
- [ ] Local-only / rate-limit policy для sensitive routes при non-localhost bind.
- [ ] OpenAPI: auth scheme documented.
- [ ] `pip-audit` / `npm audit` в `release` gate (high/critical без documented exception).
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

- [ ] Message catalog (лёгкий JSON или `react-i18next`). *(JSON catalog in `CoreModules/Localization`)*
- [ ] Вынести strings **после** split крупных tabs (трек D) — иначе двойная работа.
- [ ] Message ids: nav, buttons, empty/error states.
- [x] Pseudo-locale smoke для overflow. *(``en-XA`` catalog + tests)*
- [ ] Разделить developer diagnostics vs user-facing text (связь с треком G).

**Готово, когда:**

- [ ] Новые strings только через catalog.
- [ ] Подключаемый non-English locale без правок компонентов.
- [ ] Pseudo-locale не ломает основные tabs.

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
2. [x] `webui_crawler_routes.py` + helpers. *(partial: `compute_source_stats`, source meta/discover helpers)*
3. [ ] `chat_completions_handler.py` (после settings resolver).
4. [ ] `manager.py`.
5. [ ] `CrawlerTab` → `RagTab` → `RagTestsTab` → `LlmProxyBuildsTab`.
6. [ ] `config/__init__.py`.
7. [ ] При каждом split — зачистка `except Exception` в затронутом модуле.

**Exit:** top-10 −40%; audit script green; drift-check required.

---

### Phase 4: Packaging (трек E)

**Цель:** чистые импорты для Docker и Linux.

- [x] Убрать `sys.path.insert` из runtime entrypoints. *(``webui_backend/app.py``, ``webui_routes.py``, ``llm_proxy_wiring.py``)*
- [ ] Editable installs / консолидация зависимостей.
- [x] Import smoke из чистого venv. *(pytest smoke tests)*
- [ ] *(добавлено)* Расширить import-linter: `api` не тянет `infrastructure` напрямую (advisory → required).

**Exit:** `pip install -e .` + `chironai` / webui стартуют без path hacks.

---

### Phase 5: Deploy & release gate (треки F + A release + G security scan)

**Цель:** переносимый stack, не только Windows workstation.

- [x] Dockerfile + compose + pinned tags.
- [x] `startup_smoke.sh` + Linux CI job. *(linux-fast job: ruff + pytest -m fast)*
- [x] `release` gate: Docker build + startup + pip-audit/npm audit. *(advisory steps)*
- [ ] Health/readiness + migration smoke.

**Exit:** `docker compose up` работает; release gate одной командой.

---

### Phase 6: Product polish (трек H + остаток G UI)

**Цель:** аудитория шире local dev.

- [x] i18n catalog на уже разбитых компонентах. *(nav labels via ``t()`` in App)*
- [ ] Pseudo-locale + layout checks.
- [ ] Actionable error states в UI.
- [ ] Release checklist в репо (короткий `RELEASE.md` — только если будете поддерживать).

**Exit:** i18n-ready; product readiness ≥90% на scorecard.

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

| Направление | Сейчас | После Ph0–2 | После Ph3–4 | Цель |
|-------------|-------:|------------:|------------:|-----:|
| Backend tests | 92% | 94% | 96% | 96% |
| Frontend tests | 8% | 45% | 70% | 75% |
| Architecture | 70% | 72% | 88% | 90% |
| Maintainability | 56% | 60% | 82% | 85% |
| Code quality tooling | 60% | 78% | 88% | 90% |
| Security | 80% | 82% | 88% | 92% |
| Deploy/ops | 36% | 40% | 55% | 85% |
| API contracts | 75% | 88% | 92% | 95% |
| i18n readiness | 5% | 5% | 10% | 70% |
| Product readiness | 70% | 75% | 85% | 92% |

## Definition of 1000

- [ ] Backend и frontend имеют **сопоставимую** регрессионную защиту (не 768 vs 0).
- [ ] Нет production god files >800 строк без documented exception в audit script.
- [ ] CoreUI: typed service layer, linted, tested, buildable.
- [ ] Python: typed на границах contracts/domain; strict gate в release.
- [ ] Runtime без `sys.path` hacks; `pip install -e .` достаточно.
- [ ] Reproducible Docker/Linux path; release gate одной командой.
- [ ] API surface: routes = OpenAPI = frontend services (drift-check required).
- [ ] Settings: один resolver; legacy покрыт тестами.
- [ ] Critical flows: correlation id + no silent pass без justification.
- [ ] Security + dependency scan в release gate.
- [ ] i18n-ready UI; pseudo-locale не ломает layout.
- [ ] **Оценка ≥950** по той же 40-параметричной шкале, что и baseline ~680.

## Быстрый старт (следующие 3 PR)

1. **PR-1 (Phase 0):** `.editorconfig` + `audit_oversized_files.py` + ruff `I` + baseline report.
2. **PR-2 (Phase 1):** settings resolver + split `test_http_endpoints.py` (один домен за PR).
3. **PR-3 (Phase 2):** ESLint/Prettier + Vitest + 5 unit tests на utils + smoke Dashboard.
