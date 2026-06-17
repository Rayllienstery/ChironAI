# Way to 1000 — Дорожная карта доведения ChironAI до 1000/1000

> Оценка проекта по 21 параметру (без чтения .md-документации, на основе
> структуры, кода, тестов, CI и метрик репозитория). Текущий балл:
> **836 / 1000**. Этот документ фиксирует текущее состояние, разрыв по каждому
> параметру и конкретные шаги к максимуму.

---

## 1. Метрики проекта (на момент оценки)

| Метрика | Значение |
|---------|----------|
| Строк исходного кода | ~119 000 (Python ~55.8k + CoreUI ~34.5k) |
| Python-файлов | 404 |
| Файлов фронтенда (CoreUI) | 187 |
| Python-тестов | 877 функций в 130 файлах |
| CoreUI-тестов | 37 файлов (vitest) |
| Коммитов | 248 |
| Контрибьюторов | 1 (Kostiantyn Kolosov) |
| Версия | 0.7.11 (`Core/core/version.py`) |
| CHANGELOG | 747 строк |

---

## 2. Текущая оценка — 836 / 1000

| # | Параметр | Вес | Балл | Разрыв | Комментарий |
|---|----------|-----|------|--------|-------------|
| 1 | Архитектура и слоистость | 80 | 72 | 8 | Гексагональная слоистость api→application→domain→infrastructure+config |
| 2 | Модульность и границы | 70 | 64 | 6 | Core/ + CoreModules/ + extensions/ разделены корректно |
| 3 | Изоляция домена (import-linter) | 50 | 47 | 3 | Контракт `domain_is_inner_layer` + guardrail-тесты |
| 4 | Тестирование Python | 80 | 70 | 10 | 877 тестов, маркеры, guardrail-тесты границ |
| 5 | Тестирование фронтенда | 40 | 32 | 8 | 37 vitest-файлов, но покрытие не полное |
| 6 | CI/CD и quality gate | 70 | 62 | 8 | Профили minimal/full/release/linux-fast, основной runner — windows |
| 7 | Линтинг и статанализ | 60 | 54 | 6 | ruff, vulture, pyright, eslint, knip, prettier |
| 8 | Безопасность | 60 | 54 | 6 | Sandbox, path-traversal/zip-bomb/symlink guards, pip-audit |
| 9 | Система расширений | 60 | 54 | 6 | Манифесты, capabilities, Docker-контракт |
| 10 | Синхронизация API-контрактов | 45 | 40 | 5 | `check_api_drift.py`, 4-точечная синхронизация |
| 11 | Документация | 45 | 30 | 15 | Есть, но местами тонкая (ARCHITECTURE ~100 строк) |
| 12 | Версионирование и CHANGELOG | 40 | 36 | 4 | CHANGELOG 747 строк, инкременты версий |
| 13 | Фронтенд-архитектура | 50 | 44 | 6 | lazy+retry, error boundary, tokens, Showcase |
| 14 | Наблюдаемость | 40 | 34 | 6 | Логи, трейсы, RAG Fusion Journal, LogsManager |
| 15 | Управление кодом / ownership | 45 | 40 | 5 | Root layout guardrail, AI_RULES, таблица владельцев |
| 16 | OpenAPI/Swagger | 25 | 22 | 3 | RESTX-спецификация, Swagger-вкладка, тесты |
| 17 | Локализация (i18n) | 20 | 12 | 8 | Только en + pseudo-locale en-XA |
| 18 | Сопровождаемость / bus factor | 40 | 18 | 22 | Один контрибьютор — критический риск |
| 19 | Размер файлов / техдолг | 30 | 18 | 12 | `apple_docs_extract.py` 2131 строк, `chat_completions_handler.py` 1202 |
| 20 | Согласованность конфигов | 30 | 16 | 14 | Дрифт: `pyproject.toml` 0.2.0 vs `version.py` 0.7.11; README упоминает устаревший `utils` |
| 21 | Docker/контейнеризация | 20 | 17 | 3 | Dockerfile, docker-compose, build smoke |
| | **ИТОГО** | **1000** | **836** | **164** | |

---

## 3. Сильные стороны

- **Инженерная дисциплина выше среднего для соло-проекта**: автоматические
  guardrail'ы границ (`root_layout_guard.py`), API-drift check, аудит
  oversized-файлов и silent-exceptions, import-linter контракт.
- **Архитектурная зрелость**: гексагональные слои с enforced-изоляцией домена,
  модульная структура с явным владением, extension-система с sandbox и
  security-проверками (path-traversal, zip-bomb, symlink).
- **Качество тестирования**: 877 Python-тестов с семантическими маркерами
  (fast/slow/api/application/domain/...), guardrail-тесты архитектурных
  инвариантов, 37 CoreUI-тестов.
- **Quality gate с профилями**: minimal/full/release/linux-fast с явными
  таймаутами и advisory-шагами.

---

## 4. Слабые места

- **Bus factor = 1**: единственный контрибьютор — главный риск.
- **Техдолг в крупных файлах**: 6 файлов >700 строк, лидер — 2131 строка.
- **Дрифт конфигов**: `pyproject.toml` (0.2.0) рассинхронизирован с реальной
  версией (0.7.11); README ссылается на устаревший пакет `utils`.
- **Документация тонкая** относительно заявленной роли «source of truth».
- **i18n минимальный**: нет реальной мультиязычности (только en + en-XA).

---

## 5. Дорожная карта к 1000 — по параметрам

Ниже — конкретные действия закрытия разрыва для каждого параметра.
Параметры сгруппированы по приоритетам (P0 — критично/быстрые победы,
P1 — среднесрочно, P2 — долгосрочно).

### Параметр 1 — Архитектура и слоистость (72 → 80, +8) [P1]
- [ ] Завершить миграцию root-level «tails» под `Core/` согласно
      `docs/MODULAR_STRUCTURE.md`; обновить `docs/legacy_map.md` по каждому
      удалённому tail.
- [ ] Перевести все межмодульные вызовы на HTTP-контракты (WUB→RAG, WUB→MD,
      WUB→CR) — убрать прямые импорты реализаций между модулями.
- [ ] Добавить архитектурный ADR (Architecture Decision Record) для каждого
      крупного решения о границах.

### Параметр 2 — Модульность и границы (64 → 70, +6) [P1]
- [ ] Полностью убрать импорты реализаций между CoreModules (только контракты
      и HTTP); добавить import-linter контракт `modules_http_only`.
- [ ] Довести целевую диаграмму data flow до фактического состояния (убрать
      расхождения с `docs/MODULAR_STRUCTURE.md`).
- [ ] Вынести общие адаптеры из `Core/infrastructure/` в `CoreModules/` где
      они стали переиспользуемыми.

### Параметр 3 — Изоляция домена (47 → 50, +3) [P0]
- [ ] Добавить import-linter контракты для всех слоёв:
      `application` ↛ `api`, `infrastructure` ↛ `api`, `domain` ↛ всё внешнее.
- [ ] Добавить guardrail-тест на отсутствие циклических импортов между
      CoreModules.
- [ ] Покрыть 100% случаев в `tests/application/test_rag_import_boundaries.py`.

### Параметр 4 — Тестирование Python (70 → 80, +10) [P1]
- [ ] Ввести порог покрытия в CI: domain ≥ 90%, application ≥ 85%,
      infrastructure ≥ 70%; gate через `pytest --cov-fail-under`.
- [ ] Добавить integration-набор, прогоняющий полный RAG-pipeline
      (embed→search→rerank→context→chat) на фикстурах.
- [ ] Добавить property-based тесты (hypothesis) для парсеров
      (`markdown_meta.py`, `apple_docs_extract.py`).
- [ ] Добавить мутационное тестирование (mutmut/cosmic-ray) для критичных
      доменных сервисов.

### Параметр 5 — Тестирование фронтенда (32 → 40, +8) [P1]
- [ ] Покрыть тестами все вкладки без `.test.*` (DockerTab, LogsTab,
      PerformanceTab, DependenciesTab, SwaggerTab, TestingTab, TokensSecurityTab,
      TemplateEditorTab, DevDocumentationTab, IndexerTester, ModelTester,
      WebCallsTester, RagTesterV2Tab, ProxyTracesTab, ProxyJournalTab,
      ProxyLogsAnalytics).
- [ ] Ввести порог покрытия CoreUI в CI (`vitest --coverage --threshold`).
- [ ] Добавить snapshot-тесты для визуальных компонентов (CoreUIShowcaseTab).

### Параметр 6 — CI/CD и quality gate (62 → 70, +8) [P1]
- [ ] Поднять Linux до parity с Windows (полный full-gate на ubuntu-latest,
      не только fast-smoke).
- [ ] Добавить matrix-тестирование Python 3.10 / 3.11 / 3.12 / 3.13.
- [ ] Добавить кэширование pip (`actions/cache` или `setup-python` cache).
- [ ] Добавить загрузку coverage-отчёта (codecov/coveralls).
- [ ] Добавить ревью-чеклист как required status check.

### Параметр 7 — Линтинг и статанализ (54 → 60, +6) [P0]
- [ ] Включить строгий набор ruff по умолчанию (`E9,F,I,B,SIM`) вместо
      минимального `E9,F,I,B`.
- [ ] Довести pyright до `strict` режима для `Core/domain/` и `Core/core/`.
- [ ] Свести vulture к нулю подтверждённых находок (или задокументировать
      каждый `# noqa` с причиной).
- [ ] Добавить mypy в release-gate как параллельный typechecker.

### Параметр 8 — Безопасность (54 → 60, +6) [P1]
- [ ] Добавить SAST-сканирование (bandit) в full-gate.
- [ ] Добавить secret-scanning (gitleaks/trufflehog) в CI и pre-commit.
- [ ] Добавить аудит CSP-заголовков и security-headers для Flask.
- [ ] Включить Dependabot/Renovate для авто-PR обновления зависимостей.
- [ ] Добавить threat-model документ для extension-sandbox.

### Параметр 9 — Система расширений (54 → 60, +6) [P1]
- [ ] Добавить подпись/верификацию манифестов расширений (хэш + опц. GPG).
- [ ] Добавить тесты enforcement capabilities (расширение не может вызвать
      capability, не заявленную в манифесте).
- [ ] Добавить тесты миграции версий расширений (api_version bump).
- [ ] Документировать модель безопасности sandbox в `docs/`.

### Параметр 10 — Синхронизация API-контрактов (40 → 45, +5) [P0]
- [ ] Генерировать TypeScript-типы для CoreUI из OpenAPI-спецификации
      (codegen), убрать ручной sync `api.js` ↔ `webui_api.py`.
- [ ] Добавить контракт-тесты, прогоняющие и клиент, и сервер против единого
      контракта.
- [ ] Сделать `check_api_drift.py` обязательным (required) шагом в minimal-gate.

### Параметр 11 — Документация (30 → 45, +15) [P1]
- [ ] Расширить `docs/ARCHITECTURE.md` до полного описания слоёв, потоков,
      границ и high-risk зон (цель ~300+ строк с диаграммами).
- [ ] Написать README для каждого CoreModule с примерами запуска/использования
      (CoreUI README сейчас 14 строк).
- [ ] Добавить `docs/CONTRIBUTING.md` с процессом: ветки, коммиты, PR, gate.
- [ ] Добавить `docs/adr/` — Architecture Decision Records.
- [ ] Авто-генерировать API-reference из RESTX/OpenAPI в `docs/api/`.
- [ ] Добавить onboarding-гайд для нового разработчика.

### Параметр 12 — Версионирование и CHANGELOG (36 → 40, +4) [P0]
- [ ] Автоматизировать bump версии + CHANGELOG через commitizen /
      semantic-release (Conventional Commits).
- [ ] Синхронизировать `pyproject.toml` version с `Core/core/version.py`
      (единый источник; см. параметр 20).
- [ ] Добавить авто-генерацию release notes из CHANGELOG для GitHub Releases.

### Параметр 13 — Фронтенд-архитектура (44 → 50, +6) [P1]
- [ ] Добавить Storybook для CoreUI Showcase (живая документация компонентов).
- [ ] Ввести budget на размер бандла (`vite build` + `rollup-plugin-visualizer`
      с порогом в CI).
- [ ] Добавить accessibility-аудит (axe-core) и a11y-тесты.
- [ ] Добавить E2E-тесты (Playwright) для ключевых потоков (RAG-запрос,
      управление расширениями).

### Параметр 14 — Наблюдаемость (34 → 40, +6) [P1]
- [ ] Ввести структурированное логирование (JSON-логи) с correlation IDs.
- [ ] Добавить metrics-эндпоинт (Prometheus `/metrics`).
- [ ] Добавить distributed tracing (OpenTelemetry) для RAG-pipeline.
- [ ] Добавить health-check эндпоинт с состоянием зависимостей (Qdrant,
      Ollama, провайдеры).

### Параметр 15 — Управление кодом / ownership (40 → 45, +5) [P0]
- [ ] Добавить `CODEOWNERS` с владельцами по директориям.
- [ ] Включить branch protection (required reviews, required status checks).
- [ ] Добавить `.github/pull_request_template.md`.
- [ ] Автоматизировать обновление таблицы владельцев корневых папок в
      `AI_RULES.md` из `root_layout_guard.py`.

### Параметр 16 — OpenAPI/Swagger (22 → 25, +3) [P0]
- [ ] Перевести спецификацию на OpenAPI 3.1.
- [ ] Добавить валидацию схемы (request/response) в контракт-тестах.
- [ ] Добавить политику deprecation в spec (`deprecated: true` + заголовки).

### Параметр 17 — Локализация (12 → 20, +8) [P2]
- [ ] Добавить реальный второй язык (ru или uk) в `catalog/`.
- [ ] Добавить i18n-lint, ловящий хардкод-строки вне `t()` в CoreUI.
- [ ] Добавить workflow перевода (extract → перевод → merge) с проверкой
      полноты ключей.
- [ ] Покрыть тестами отсутствие untranslated-ключей.

### Параметр 18 — Сопровождаемость / bus factor (18 → 40, +22) [P2]
- [ ] Привлечь второго контрибьютора / рецензента (критично для bus factor).
- [ ] Задокументировать tribal knowledge: неочевидные решения, legacy-хвосты,
      high-risk зоны — в `docs/legacy_map.md` и ADR.
- [ ] Внедрить парное программирование / обязательный review на PR.
- [ ] Добавить runbook для инцидентов и восстановления.
- [ ] Записать архитектурные walkthrough-видео/тексты для онбординга.
- [ ] Ввести «knowledge transfer» сессии и кросс-ревью модулей.

### Параметр 19 — Размер файлов / техдолг (18 → 30, +12) [P1]
- [ ] Расщепить `apple_docs_extract.py` (2131 строк) по responsibility
      (fetcher / parser / model / markdown-builder).
- [ ] Расщепить `chat_completions_handler.py` (1202) и `tool_helpers.py`
      (1176) на когезивные модули.
- [ ] Расщепить `rag_tests_routes.py` (1357) и `v1_blueprint.py` (1063).
- [ ] Ввести hard-лимит размера файла в CI (например, 500 строк) через
      `scripts/audit_oversized_files.py --mode check` как required шаг.

### Параметр 20 — Согласованность конфигов (16 → 30, +14) [P0]
- [ ] Синхронизировать `pyproject.toml` version = `Core/core/version.py`
      VERSION (единый источник истины; убрать дрифт 0.2.0 vs 0.7.11).
- [ ] Исправить README: убрать ссылку на устаревший пакет `utils`;
      актуализировать список пакетов под `Core/`.
- [ ] Добавить CI-проверку дрифта версии между `pyproject.toml`,
      `version.py`, `CHANGELOG.md` последней записью.
- [ ] Добавить pre-commit hooks (ruff, prettier, version-sync, lockfile-check).
- [ ] Добавить `check_config_drift.py` в minimal-gate.

### Параметр 21 — Docker/контейнеризация (17 → 20, +3) [P1]
- [ ] Оптимизировать Dockerfile (multi-stage, slim runtime, кэш слоёв).
- [ ] Добавить `HEALTHCHECK` в Dockerfile.
- [ ] Добавить `docker-compose.yml` для полного стека (app + Qdrant + Ollama)
      с healthcheck-зависимостями.
- [ ] Добавить сканирование образа (trivy) в release-gate.

---

## 6. План по фазам

### Фаза 0 — Быстрые победы (P0, ~+50 баллов, 1–2 недели)
Цель: закрыть дешёвые, высокодоходные разрывы без архитектурных изменений.

| Параметр | Действие | +Балл |
|----------|----------|-------|
| 20 | Синхронизация версии `pyproject.toml`↔`version.py`, фикс README, pre-commit, config-drift CI | +14 |
| 3 | Дополнительные import-linter контракты для всех слоёв | +3 |
| 7 | Строгий ruff + pyright strict для domain/core | +6 |
| 10 | Codegen TS-типов из OpenAPI, обязательный drift-check | +5 |
| 12 | Автоматизация bump + CHANGELOG (commitizen) | +4 |
| 15 | CODEOWNERS, PR-template, branch protection | +5 |
| 16 | OpenAPI 3.1 + валидация схемы | +3 |
| 19 | Hard-лимит размера файла в CI (required) | +4 |
| 4 | Порог покрытия domain/application в CI | +2 |

**Итог Фазы 0: ~886 / 1000**

### Фаза 1 — Среднесрочные улучшения (P1, ~+80 баллов, 1–3 месяца)
Цель: архитектурная и качественная зрелость.

| Параметр | Действие | +Балл |
|----------|----------|-------|
| 1 | Завершение миграции tails под Core/, HTTP-контракты между модулями | +8 |
| 2 | Убрать импорты реализаций между CoreModules | +6 |
| 4 | Integration-набор RAG-pipeline, property-based тесты, пороги покрытия | +8 |
| 5 | Покрытие тестами всех вкладок CoreUI, порог покрытия | +8 |
| 6 | Linux parity, matrix Python, кэш pip, coverage upload | +8 |
| 8 | SAST (bandit), secret-scanning, Dependabot, CSP-аудит | +6 |
| 9 | Подпись манифестов, enforcement capabilities, тесты миграции | +6 |
| 11 | Расширение ARCHITECTURE.md, README модулей, CONTRIBUTING, ADR | +15 |
| 13 | Storybook, budget бандла, a11y-аудит, E2E (Playwright) | +6 |
| 14 | Структурированные логи, Prometheus, OpenTelemetry, health-check | +6 |
| 19 | Расщепление крупных файлов (apple_docs_extract, chat_completions) | +8 |
| 21 | Multi-stage Dockerfile, HEALTHCHECK, compose-стек, trivy | +3 |

**Итог Фазы 1: ~966 / 1000**

### Фаза 2 — Долгосрочные/стратегические (P2, ~+34 балла, 3–6+ месяцев)
Цель: устойчивость и масштабируемость команды.

| Параметр | Действие | +Балл |
|----------|----------|-------|
| 17 | Второй язык (ru/uk), i18n-lint, workflow переводов | +8 |
| 18 | Второй контрибьютор, документирование tribal knowledge, runbook, KT | +22 |
| 4 | Мутационное тестирование критичных сервисов | +2 |
| 7 | mypy в release-gate, vulture к нулю | +2 |

**Итог Фазы 2: 1000 / 1000**

---

## 7. Метрики успеха

| Метрика | Сейчас | Цель (1000) |
|---------|--------|-------------|
| Суммарный балл | 836 | 1000 |
| Контрибьюторов | 1 | ≥ 2 |
| Макс. размер Python-файла | 2131 строк | ≤ 500 строк |
| Дрифт версии pyproject↔version.py | есть | 0 |
| Покрытие domain | не задано | ≥ 90% |
| Покрытие application | не задано | ≥ 85% |
| Покрытие CoreUI | не задано | ≥ 70% |
| Языков i18n | 1 (en) | ≥ 2 |
| import-linter контрактов | 1 | ≥ 4 |
| Linux CI parity | fast-only | full parity |
| Python matrix | 3.12 | 3.10–3.13 |
| Документация ARCHITECTURE.md | ~100 строк | ~300+ строк |
| ADR | 0 | ≥ 5 |

---

## 8. Риски на пути к 1000

- **Bus factor = 1** — параметр 18 даёт максимальный разрыв (+22) и最难 всего
  закрывается: требует привлечения человека, а не только инженерных усилий.
  Без второго контрибьютора 1000 недостижимо (максимум ~978).
- **Расщепление крупных файлов** (параметр 19) несёт риск регрессий в
  high-risk зонах (LlmProxy, RAG) — требует тщательного тестирования.
- **Codegen из OpenAPI** (параметр 10) меняет workflow CoreUI — нужен период
  сосуществования ручного и сгенерированного клиента.
- **Автоматизация версионирования** (параметр 12) требует перехода на
  Conventional Commits — дисциплина коммитов.

---

## 9. Приоритезация (что делать первым)

1. **Синхронизация версии и фикс README** (параметр 20) — 0 усилий, +14 баллов.
2. **Строгий lint + import-linter контракты** (параметры 3, 7) — низкий риск,
   +9 баллов.
3. **Hard-лимит размера файла + расщепление лидеров** (параметр 19) —
   средний риск, +12 баллов.
4. **Пороги покрытия в CI** (параметры 4, 5) — средний риск, +18 баллов.
5. **Документация + ADR** (параметр 11) — низкий риск, +15 баллов.
6. **Второй контрибьютор** (параметр 18) — организационно, +22 балла.

---

*Документ сгенерирован на основе структурного анализа репозитория без чтения
.md-документации. Баллы — экспертная оценка, не автоматический замер.*