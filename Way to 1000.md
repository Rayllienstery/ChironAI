# Way to 1000 — Исполняемый план для ИИ-агента

> **Назначение:** этот документ — не человекочитаемый roadmap, а
> **машинно-исполняемый план**. Каждая задача имеет ID, точные пути файлов,
> исполняемые шаги, команды верификации, зависимости и критерий готовности.
> ИИ-агент должен выполнять задачи последовательно по топологическому
> порядку, после каждой задачи запускать её gate верификации и не переходить
> дальше, пока gate не пройден.
>
> **Текущий балл: 836 / 1000. Цель: 1000 / 1000. Разрыв: +164.**

---

## 0. Правила исполнения (обязательны для агента)

1. **Соблюдай `AI_RULES.md` и `AGENTS.md`** — границы слоёв, ownership, WebUI
   API sync в 4 местах, CoreUI Showcase sync, version bump + CHANGELOG.
2. **Одна задача = один коммит** (если явно не указано иное). Не объединяй
   независимые задачи в один коммит.
3. **После каждой задачи, меняющей non-`.md` файл:** bump версии в
   `Core/core/version.py` (`X.Y.Z` → `X.Y.(Z+1)`), добавить запись в
   `CHANGELOG.md` (что сделано, не как), проверить запуск через
   `build_and_run.bat` (или явно указать причину, если не запущен).
4. **Gate верификации обязателен.** Команда в блоке `VERIFY:` должна вернуть
   exit 0. Если gate падает — задача не завершена.
5. **Не выдумывай API/поведение.** Если в задаче не хватает фактов — используй
   Grep/Read/Glob для проверки реального состояния перед редактированием.
6. **Расщепление файлов (P1-T19):** сохраняй публичный импортный контракт
   (внешние импорты не должны ломаться). Реэкспорт из facade-модуля.
7. **CoreUI JSX:** после любого изменения `.jsx/.tsx` запускай
   `npm run build` в `CoreModules/CoreUI` (или эквивалентный lint/parser-чек)
   и обновляй `CoreUIShowcaseTab.jsx` при добавлении/удалении UI.
8. **Не коммить и не пушь** без явного запроса пользователя.
9. **Координаты репозитория:** root = `C:\Users\Raylee\AI`; CoreUI =
   `CoreModules/CoreUI`; shared contracts = `Core/core/contracts/`.

### Базовые команды верификации (используются в задачах)

```
PY_LINT        = ruff check .
PY_FAST_TESTS  = pytest -q -m fast --maxfail=1
PY_COLLECT     = pytest --collect-only -q
PY_FULL        = pytest -q
PY_VULTURE     = python -m vulture
PY_IMPORTS     = lint-imports
PY_API_DRIFT   = python scripts/check_api_drift.py --strict --strict-openapi
PY_OVERSIZED   = python scripts/audit_oversized_files.py --mode check
PY_ROOT_GUARD  = python scripts/root_layout_guard.py
UI_BUILD       = npm run build            (cwd: CoreModules/CoreUI)
UI_LINT        = npm run lint             (cwd: CoreModules/CoreUI)
UI_TEST        = npm run test -- --run    (cwd: CoreModules/CoreUI)
UI_TYPECHECK   = npm run typecheck        (cwd: CoreModules/CoreUI)
UI_KNIP        = npm run knip             (cwd: CoreModules/CoreUI)
GATE_MINIMAL   = python scripts/quality_gate.py --profile minimal
GATE_FULL      = python scripts/quality_gate.py --profile full
SMOKE          = .\build_and_run.bat      (cwd: repo root)
```

---

## 0.5 Мастер Todo-лист (трекинг исполнения)

> Агент ведёт этот список: отмечает `[x]` после прохождения gate задачи,
> `[~]` — в работе, `[!]` — заблокировано. Статус фазы = «все задачи `[x]`».
> После каждого изменения перечитывает файл и обновляет только свою строку.

### Фаза 0 — P0 (быстрые победы, ≈+45 → ~881)

- [x] **T20.1** Синхронизировать версию pyproject↔version.py · +4 · deps: —
- [x] **T20.2** Исправить устаревшие ссылки в README · +3 · deps: —
- [x] **T20.3** CI-проверка дрифта версии · +4 · deps: T20.1
- [x] **T20.4** Pre-commit hooks · +3 · deps: T20.1
- [x] **T3.1** Расширить import-linter контракты для всех слоёв · +3 · deps: —
- [x] **T7.1** Строгий ruff (SIM) · +3 · deps: —
- [x] **T7.2** pyright strict для domain/core · +2 · deps: T7.1
- [x] **T10.1** check_api_drift → required в minimal-gate · +2 · deps: —
- [x] **T10.2** Codegen TS-типов из OpenAPI · +3 · deps: T10.1
- [x] **T12.1** Автоматизация bump + CHANGELOG (commitizen) · +4 · deps: T20.1
- [x] **T15.1** CODEOWNERS + PR template · +5 · deps: —
- [x] **T16.1** OpenAPI 3.1 + валидация схемы · +3 · deps: T10.1
- [x] **T19.1** Hard-лимит размера файла (required) · +4 · deps: —
- [x] **T4.1** Порог покрытия domain/application в CI · +2 · deps: —

### Фаза 1 — P1 (среднесрочные, ≈+83 → ~964)

- [x] **T19.2** Расщепить apple_docs_extract.py (2131) · +3 · deps: T19.1
- [x] **T19.3** Расщепить chat_completions_handler + tool_helpers · +3 · deps: T19.1
- [x] **T19.4** Расщепить rag_tests_routes + v1_blueprint · +2 · deps: T19.1
- [x] **T1.1** Завершить миграцию root-level tails под Core/ · +4 · deps: T3.1
- [x] **T2.1** Убрать импорты реализаций между CoreModules · +3 · deps: T3.1
- [x] **T1.2** ADR для архитектурных решений (≥5) · +4 · deps: —
- [x] **T4.2** Integration-набор полного RAG-pipeline · +4 · deps: T4.1
- [x] **T4.3** Property-based тесты для парсеров · +2 · deps: T4.1
- [x] **T5.1** Покрыть тестами вкладки CoreUI без тестов · +5 · deps: —
- [x] **T5.2** Порог покрытия CoreUI в CI (70%) · +3 · deps: T5.1
- [x] **T6.1** Linux parity + matrix Python + кэш + codecov · +8 · deps: —
- [x] **T8.1** SAST + secret-scanning + Dependabot + CSP · +6 · deps: —
- [x] **T9.1** Подпись манифестов + enforcement + тесты миграции · +6 · deps: —
- [x] **T11.1** Расширить ARCHITECTURE.md (≥300 строк) · +5 · deps: —
- [x] **T11.2** README для каждого CoreModule · +4 · deps: —
- [x] **T11.3** CONTRIBUTING + onboarding · +3 · deps: T12.1
- [x] **T11.4** Авто-генерация API-reference из OpenAPI · +3 · deps: T16.1
- [x] **T13.1** Storybook + bundle budget + a11y + E2E · +6 · deps: T5.1
- [x] **T14.1** Структурированные логи + Prometheus + OTel + health · +6 · deps: —
- [ ] **T21.1** Docker: trivy-скан + Ollama в compose · +3 · deps: —

### Фаза 2 — P2 (стратегические, ≈+34 → 1000)

- [ ] **T17.1** Второй язык i18n (ukrainian), возможность переключения в Settings + i18n-lint + workflow · +8 · deps: —
- [ ] **T18.1** Документирование tribal knowledge · +10 · deps: T1.2
- [!] **T18.2** Второй контрибьютор (ЧЕЛОВЕК — не ИИ-задача) · +12 · deps: T18.1
- [ ] **T4.4** Мутационное тестирование критичных сервисов · +2 · deps: T4.2
- [ ] **T7.3** mypy в release-gate + vulture к нулю · +2 · deps: T7.2

### Сводка по статусу

| Фаза | Задач | +Балл | Статус |
|------|-------|-------|--------|
| 0 (P0) | 14 | ≈45 | 0/14 |
| 1 (P1) | 20 | ≈83 | 0/20 |
| 2 (P2) | 5 | ≈34 | 0/5 (1 заблокировано) |
| **Итого** | **39** | **≈162** | **0/39** |

> **Примечание о сумме:** сумма +Балл по задачам ≈162; разрыв оценки = 164.
> Расхождение (≈2) — округление фазовых итогов в разделе 6. Точный потолок
> без T18.2 = 836 + 150 = **986/1000** (см. раздел 7).

---

## 1. Контекст и метрики (фактическое состояние)

| Метрика | Значение | Источник |
|---------|----------|----------|
| Версия (истина) | 0.7.11 | `Core/core/version.py:3` |
| Версия (pyproject, ДРИФТ) | 0.2.0 | `pyproject.toml:7` |
| Python-строк | ~55 855 | 404 файла |
| CoreUI-строк | ~34 476 | 187 файлов |
| Python-тестов | 877 | 130 файлов |
| CoreUI-тестов | 37 файлов | vitest |
| Коммитов / контрибьюторов | 248 / 1 | git |
| import-linter контрактов | 1 | `pyproject.toml:181-185` |
| Oversized-лимит | prod 800 / test 1200 | `scripts/audit_oversized_files.py:12-13` |
| Документированные oversized-исключения | 22 файла | `audit_oversized_files.py:32-54` |
| i18n-локали | en, en-XA | `CoreModules/CoreUI/src/services/i18n.js:10-13` |
| Dockerfile | multi-stage + HEALTHCHECK | `Dockerfile:46-47` |
| docker-compose | qdrant + app + healthchecks | `docker-compose.yml` |

### Текущая оценка — 836 / 1000

| # | Параметр | Вес | Балл | Разрыв |
|---|----------|-----|------|--------|
| 1 | Архитектура и слоистость | 80 | 72 | 8 |
| 2 | Модульность и границы | 70 | 64 | 6 |
| 3 | Изоляция домена (import-linter) | 50 | 47 | 3 |
| 4 | Тестирование Python | 80 | 70 | 10 |
| 5 | Тестирование фронтенда | 40 | 32 | 8 |
| 6 | CI/CD и quality gate | 70 | 62 | 8 |
| 7 | Линтинг и статанализ | 60 | 54 | 6 |
| 8 | Безопасность | 60 | 54 | 6 |
| 9 | Система расширений | 60 | 54 | 6 |
| 10 | Синхронизация API-контрактов | 45 | 40 | 5 |
| 11 | Документация | 45 | 30 | 15 |
| 12 | Версионирование и CHANGELOG | 40 | 36 | 4 |
| 13 | Фронтенд-архитектура | 50 | 44 | 6 |
| 14 | Наблюдаемость | 40 | 34 | 6 |
| 15 | Управление кодом / ownership | 45 | 40 | 5 |
| 16 | OpenAPI/Swagger | 25 | 22 | 3 |
| 17 | Локализация (i18n) | 20 | 12 | 8 |
| 18 | Сопровождаемость / bus factor | 40 | 18 | 22 |
| 19 | Размер файлов / техдолг | 30 | 18 | 12 |
| 20 | Согласованность конфигов | 30 | 16 | 14 |
| 21 | Docker/контейнеризация | 20 | 17 | 3 |
| | **ИТОГО** | **1000** | **836** | **164** |

---

## 2. Задачи — Фаза 0 (P0, быстрые победы, ~+50 → 886)

Задачи Фазы 0 не требуют архитектурных изменений. Выполнять в указанном
порядке (есть зависимости).

---

### T20.1 — Синхронизировать версию pyproject.toml ↔ version.py
**Параметр:** 20 | **Приоритет:** P0 | **Зависит от:** — | **+Балл:** 4

**Файлы:**
- `pyproject.toml:7` — `version = "0.2.0"` → синхронизировать с `Core/core/version.py`
- `Core/core/version.py` — источник истины

**Шаги:**
1. Read `Core/core/version.py`, взять `VERSION`.
2. Edit `pyproject.toml:7`: `version = "0.2.0"` → `version = "<VERSION>"`.
3. Bump `Core/core/version.py` VERSION `0.7.11` → `0.7.12` (задача меняет non-md файл).
4. Добавить запись в `CHANGELOG.md` (Fixed: синхронизация версии pyproject).

**VERIFY:**
```
# версия совпадает в двух файлах
$v = (Get-Content Core\core\version.py | Select-String 'VERSION = "([^"]+)"').Matches.Groups[1].Value
$p = (Get-Content pyproject.toml | Select-String '^version = "([^"]+)"').Matches.Groups[1].Value
"$v $p"   # должны быть равны
```
**Критерии готовности:**
- [ ] `$v -eq $p` → True

---

### T20.2 — Исправить устаревшие ссылки в README
**Параметр:** 20 | **Приоритет:** P0 | **Зависит от:** — | **+Балл:** 3

**Файлы:** `README.md:28` — упоминает устаревший пакет `utils`.

**Шаги:**
1. Grep `utils` в `README.md` — найти строку с `(packages: ..., utils)`.
2. Заменить список пакетов на актуальный из `pyproject.toml:65-76`
   (`application, api, config, core, domain, infrastructure` — без `utils`).
3. Проверить остальные ссылки в README на актуальность (console scripts
   `tmrag`/`chironai` → `api.cli`).

**VERIFY:** `grep -n "utils" README.md` → нет совпадений в контексте пакетов.
**Критерии готовности:**
- [ ] README не ссылается на несуществующий пакет `utils`

---

### T20.3 — CI-проверка дрифта версии (config-drift guard)
**Параметр:** 20 | **Приоритет:** P0 | **Зависит от:** T20.1 | **+Балл:** 4

**Файлы:**
- `scripts/check_version_drift.py` (СОЗДАТЬ)
- `scripts/quality_gate.py` — добавить шаг в `MINIMAL_GATE`
- `tests/scripts/test_version_drift.py` (СОЗДАТЬ)

**Шаги:**
1. Создать `scripts/check_version_drift.py`: читать `Core/core/version.py`
   VERSION, `pyproject.toml` `[project].version`, последнюю запись
   `CHANGELOG.md` (`## [X.Y.Z]`); exit 1 если не совпадают.
2. Добавить `GateStep("version-drift", _python_command("scripts/check_version_drift.py"), REPO_ROOT, 30)` в `MINIMAL_GATE` (после ruff).
3. Создать `tests/scripts/test_version_drift.py` — unit-тесты парсинга.
4. Bump версии + CHANGELOG.

**VERIFY:** `python scripts/check_version_drift.py` → exit 0; `GATE_MINIMAL` проходит.
**Критерии готовности:**
- [ ] дрифт версии детектируется автоматически в minimal-gate

---

### T20.4 — Pre-commit hooks
**Параметр:** 20 | **Приоритет:** P0 | **Зависит от:** T20.1 | **+Балл:** 3

**Файлы:**
- `.pre-commit-config.yaml` (СОЗДАТЬ)
- `scripts/check_version_drift.py` (из T20.3)

**Шаги:**
1. Создать `.pre-commit-config.yaml` с hooks: ruff (`ruff check .`),
   ruff-format (`ruff format --check .`), prettier (CoreUI), version-drift
   (`scripts/check_version_drift.py`), lockfile-check
   (`git diff --exit-code HEAD -- CoreModules/CoreUI/package-lock.json`).
2. Bump версии + CHANGELOG.

**VERIFY:** `pre-commit run --all-files` (если pre-commit установлен) или
ручная проверка конфига на валидность YAML.
**Критерии готовности:**
- [ ] `.pre-commit-config.yaml` существует и валиден

---

### T3.1 — Расширить import-linter контракты для всех слоёв
**Параметр:** 3 | **Приоритет:** P0 | **Зависит от:** — | **+Балл:** 3

**Файлы:** `pyproject.toml:177-185` (секция `[tool.importlinter]`).

**Шаги:**
1. Read текущий контракт `domain_is_inner_layer`.
2. Добавить контракты (type = `forbidden`):
   - `application_not_import_api`: source `application`, forbidden `api`.
   - `infrastructure_not_import_api`: source `infrastructure`, forbidden `api`.
   - `domain_is_inner_layer` (уже есть) — оставить.
3. Запустить `lint-imports`; если новые контракты падают на реальных
   нарушениях — НЕ ослаблять контракт, а исправить нарушения (вынести
   нарушающий импорт за слой или через порт). Если нарушение в legacy-tail —
   задокументировать в `docs/legacy_map.md` и временно исключить с TODO.
4. Bump версии + CHANGELOG.

**VERIFY:** `lint-imports` → exit 0.
**Критерии готовности:**
- [ ] ≥3 контракта import-linter
- [ ] все проходят

---

### T7.1 — Строгий ruff по умолчанию
**Параметр:** 7 | **Приоритет:** P0 | **Зависит от:** — | **+Балл:** 3

**Файлы:** `pyproject.toml:160-162` (`[tool.ruff.lint]`).

**Шаги:**
1. Текущее: `select = ["E9", "F", "I", "B"]`, `ignore = [...]`.
2. Добавить `"SIM"` в select: `select = ["E9", "F", "I", "B", "SIM"]`.
3. Запустить `ruff check . --select SIM` — собрать нарушения.
4. Исправить auto-fixable (`ruff check . --select SIM --fix`).
5. Оставшиеся ручные нарушения — исправить или добавить в `ignore` с
   комментарием-причиной (только если исправление рискованно).
6. Bump версии + CHANGELOG.

**VERIFY:** `ruff check .` → exit 0.
**Критерии готовности:**
- [ ] SIM включён
- [ ] ruff чист

---

### T7.2 — pyright strict для domain/core
**Параметр:** 7 | **Приоритет:** P0 | **Зависит от:** T7.1 | **+Балл:** 2

**Файлы:** `pyrightconfig.json`.

**Шаги:**
1. Read `pyrightconfig.json`.
2. Добавить override для `Core/domain/**` и `Core/core/**` с
   `"typeCheckingMode": "strict"`.
3. Запустить `python -m pyright` — собрать ошибки strict-режима.
4. Исправить type-ошибки в domain/core (добавить аннотации, `Any` → конкретные
   типы). Если файл в legacy-tail — задокументировать исключение.
5. Bump версии + CHANGELOG.

**VERIFY:** `python -m pyright` → exit 0.
**Критерии готовности:**
- [ ] domain/core под strict
- [ ] pyright чист

---

### T10.1 — Сделать check_api_drift обязательным (required) в minimal-gate
**Параметр:** 10 | **Приоритет:** P0 | **Зависит от:** — | **+Балл:** 2

**Файлы:** `scripts/quality_gate.py:38-45` (`MINIMAL_GATE`).

**Шаги:**
1. Текущее: `api-drift-check` есть только в `FULL_GATE_EXTRA` (required=True).
2. Добавить в `MINIMAL_GATE`:
   `GateStep("api-drift", _python_command("scripts/check_api_drift.py", "--strict", "--strict-openapi"), REPO_ROOT, 60)`.
3. Запустить drift-check; если падает — устранить дрифт (синхронизировать
   frontend↔Flask↔OpenAPI по правилу 4-точечной синхронизации из AI_RULES).
4. Bump версии + CHANGELOG.

**VERIFY:** `python scripts/check_api_drift.py --strict --strict-openapi` → exit 0; `GATE_MINIMAL` проходит.
**Критерии готовности:**
- [ ] API-drift — required шаг minimal-gate

---

### T10.2 — Codegen TypeScript-типов из OpenAPI
**Параметр:** 10 | **Приоритет:** P0 | **Зависит от:** T10.1 | **+Балл:** 3

**Файлы:**
- `CoreModules/CoreUI/scripts/gen_api_types.mjs` (СОЗДАТЬ)
- `CoreModules/CoreUI/src/services/api.types.ts` (ГЕНЕРИРУЕТСЯ)
- `CoreModules/CoreUI/package.json` — добавить script `gen:types`
- `Core/core/openapi.py` — убедиться, что spec строится (источник)

**Шаги:**
1. Добавить endpoint или CLI, экспортирующий OpenAPI JSON
   (`build_openapi_spec(app)` уже есть в `Core/core/openapi.py`).
2. Создать `gen_api_types.mjs`: fetch `/api/webui/openapi.json` (или читать
   из файла), сгенерировать TS-типы (через `openapi-typescript` — добавить в
   devDeps) → `src/services/api.types.ts`.
3. Добавить `"gen:types": "node scripts/gen_api_types.mjs"` в package.json.
4. В `api.js` импортировать типы где возможно (постепенно; не ломать
   существующий JS).
5. Добавить `gen:types` в `coreui-build` или pre-build шаг.
6. Bump версии + CHANGELOG.

**VERIFY:** `npm run gen:types` → создаёт `api.types.ts`; `UI_BUILD` проходит.
**Критерии готовности:**
- [ ] TS-типы генерируются из единого источника (OpenAPI)

---

### T12.1 — Автоматизация bump версии + CHANGELOG (commitizen)
**Параметр:** 12 | **Приоритет:** P0 | **Зависит от:** T20.1 | **+Балл:** 4

**Файлы:**
- `pyproject.toml` — добавить `[tool.commitizen]`
- `.cz.toml` или секция в pyproject
- `scripts/sync_version.py` (СОЗДАТЬ) — bump `version.py` + `pyproject.toml` + CHANGELOG

**Шаги:**
1. Добавить `[tool.commitizen]` в `pyproject.toml`: name=chironai,
   version=0.7.x, version_files=["Core/core/version.py:VERSION",
   "pyproject.toml:version"], changelog_file=CHANGELOG.md.
2. Создать `scripts/sync_version.py`: `cz bump --yes` обёртка, проверяющая
   синхронизацию после bump.
3. Документировать Conventional Commits формат в `docs/CONTRIBUTING.md`
   (см. T11.3).
4. Bump версии + CHANGELOG.

**VERIFY:** `python scripts/sync_version.py --dry-run` (или `cz bump --dry-run`)
→ показывает корректный следующий bump.
**Критерии готовности:**
- [ ] bump автоматизирован
- [ ] version_files синхронны

---

### T15.1 — CODEOWNERS + PR template
**Параметр:** 15 | **Приоритет:** P0 | **Зависит от:** — | **+Балл:** 5

**Файлы:**
- `.github/CODEOWNERS` (СОЗДАТЬ)
- `.github/pull_request_template.md` (СОЗДАТЬ)

**Шаги:**
1. Создать `.github/CODEOWNERS` с владельцами по директориям:
   `Core/` `@kostiantyn-kolosov`, `CoreModules/CoreUI/` `@kostiantyn-kolosov`,
   `CoreModules/LlmProxy/` `@kostiantyn-kolosov`, `extensions/` `@kostiantyn-kolosov`,
   `docs/` `@kostiantyn-kolosov`, `tests/` `@kostiantyn-kolosov`.
2. Создать `.github/pull_request_template.md` с чек-листом из AI_RULES
   секция 9 (WebUI API sync, RESTX, import-границы, CoreUI Showcase, version
   bump, build_and_run).
3. Bump версии + CHANGELOG.

**VERIFY:** файлы существуют и валидны.
**Критерии готовности:**
- [ ] CODEOWNERS + PR template на месте

---

### T16.1 — OpenAPI 3.1 + валидация схемы
**Параметр:** 16 | **Приоритет:** P0 | **Зависит от:** T10.1 | **+Балл:** 3

**Файлы:**
- `Core/core/openapi.py` — версия spec → 3.1.x
- `tests/api/test_openapi_spec.py` (СОЗДАТЬ или расширить)

**Шаги:**
1. Read `Core/core/openapi.py`, найти где задаётся `openapi` версия поля.
2. Изменить на `"3.1.0"`.
3. Проверить, что flask-restx / ручной builder совместим с 3.1 (nullable →
   type array, и т.д.); исправить несовместимости.
4. Создать/расширить тест: валидация spec через `openapi-spec-validator`
   (добавить в requirements-dev.txt `[dev]`).
5. Bump версии + CHANGELOG.

**VERIFY:** `pytest tests/api/test_openapi_spec.py -q` → pass; spec валиден по 3.1.
**Критерии готовности:**
- [ ] OpenAPI 3.1
- [ ] валидация в тестах

---

### T19.1 — Hard-лимит размера файла как required шаг
**Параметр:** 19 | **Приоритет:** P0 | **Зависит от:** — | **+Балл:** 4

**Файлы:** `scripts/quality_gate.py` — `oversized-files` уже в FULL_GATE_EXTRA
как `required=False` (advisory).

**Шаги:**
1. В `FULL_GATE_EXTRA` изменить `oversized-files` на `required=True`.
2. Запустить `python scripts/audit_oversized_files.py --mode check` —
   собрать undocumented-нарушения.
3. Для каждого undocumented-нарушения: либо расщепить файл (см. T19.2+),
   либо добавить в `DOCUMENTED_EXCEPTIONS` с причиной (только если расщепление
   рискованно и запланировано в P1).
4. Bump версии + CHANGELOG.

**VERIFY:** `python scripts/audit_oversized_files.py --mode check` → exit 0
(нет undocumented); `GATE_FULL` проходит.
**Критерии готовности:**
- [ ] oversized-files — required
- [ ] нет undocumented-нарушений

---

### T4.1 — Порог покрытия domain/application в CI
**Параметр:** 4 | **Приоритет:** P0 | **Зависит от:** — | **+Балл:** 2

**Файлы:**
- `scripts/quality_gate.py` — добавить шаг coverage-gate
- `pyproject.toml` — `[tool.coverage.report]` (опц.)

**Шаги:**
1. Добавить в `FULL_GATE_EXTRA`:
   `GateStep("coverage-domain", ("pytest", "-q", "-m", "fast", "--cov=domain", "--cov=application", "--cov-fail-under=80"), REPO_ROOT, 300, required=True)`.
2. Запустить — если <80%, поднять покрытие критичных модулей domain/application
   тестами (не ослаблять порог ниже 80 на старте; цель 90/85 в P1).
3. Bump версии + CHANGELOG.

**VERIFY:** coverage-gate проходит в `GATE_FULL`.
**Критерии готовности:**
- [ ] coverage-fail-under=80 для domain+application

---

**ИТОГ ФАЗЫ 0: ~886 / 1000** (после всех P0-задач)

---

## 3. Задачи — Фаза 1 (P1, среднесрочные, ~+80 → 966)

Фаза 1 требует архитектурных изменений и тщательного тестирования.
Каждое расщепление файла — отдельный коммит с полным gate.

---

### T19.2 — Расщепить apple_docs_extract.py (2131 строк)
**Параметр:** 19 | **Приоритет:** P1 | **Зависит от:** T19.1 | **+Балл:** 3

**Файлы:**
- `Core/modules/webui_backend/webui_backend/apple_docs_extract.py` (2131 строк)
- СОЗДАТЬ: `apple_docs_models.py`, `apple_docs_parser.py`,
  `apple_docs_markdown.py` (или подпакет `apple_docs/`)
- `apple_docs_extract.py` → facade, реэкспорт публичных имён

**Шаги:**
1. Read весь файл, составить карту responsibility: dataclasses (модели),
   парсинг HTML (parser), сборка markdown (builder), оркестрация (extract).
2. Вынести dataclasses (`AppleDocBlock`, `AppleDocSection`, `AppleDocPage`) →
   `apple_docs_models.py`.
3. Вынести функции парсинга (`_extract_text`, `_parse_table_to_markdown`,
   секции) → `apple_docs_parser.py`.
4. Вынести сборку markdown → `apple_docs_markdown.py`.
5. `apple_docs_extract.py` → facade: импорты + `__all__` (сохранить публичный
   контракт — внешние импорты `from webui_backend.apple_docs_extract import X`
   не должны ломаться).
6. Убрать путь из `DOCUMENTED_EXCEPTIONS` в `audit_oversized_files.py`.
7. Запустить тесты webui_backend + `GATE_FULL`.
8. Bump версии + CHANGELOG.

**VERIFY:** `PY_FULL` pass; `PY_OVERSIZED` не сообщает apple_docs_extract;
каждый новый файл ≤ 800 строк.
**Критерии готовности:**
- [ ] apple_docs_extract ≤ 800
- [ ] контракт сохранён

---

### T19.3 — Расщепить chat_completions_handler.py (1202) и tool_helpers.py (1176)
**Параметр:** 19 | **Приоритет:** P1 | **Зависит от:** T19.1 | **+Балл:** 3

**Файлы:**
- `CoreModules/LlmProxy/llm_proxy/chat_completions_handler.py`
- `CoreModules/LlmProxy/llm_proxy/tool_helpers.py`
- СОЗДАТЬ когезивные подмодули (по responsibility: streaming, vision,
  reasoning, tool-bridge)

**Шаги:** аналогично T19.2 — карта responsibility → вынос → facade с
реэкспортом → убрать из DOCUMENTED_EXCEPTIONS → `GATE_FULL` (включая
`tests/llm_proxy/`) → bump.
**VERIFY:** `PY_FULL` pass (особенно `tests/llm_proxy/`); файлы ≤ 800.
**Критерии готовности:**
- [ ] оба файла ≤ 800
- [ ] контракт сохранён

---

### T19.4 — Расщепить rag_tests_routes.py (1357) и v1_blueprint.py (1063)
**Параметр:** 19 | **Приоритет:** P1 | **Зависит от:** T19.1 | **+Балл:** 2

**Файлы:**
- `Core/api/http/rag_tests_routes.py` (1357)
- `CoreModules/LlmProxy/llm_proxy/v1_blueprint.py` (1063)

**Шаги:** аналогично T19.2. Для routes — разбить по ресурсам (collections,
runs, results). Для v1_blueprint — по endpoint-группам (chat, models,
messages, responses). Сохранить Flask-регистрацию контракта.
**VERIFY:** `PY_FULL` pass (включая `tests/api/`); `PY_API_DRIFT` pass; файлы ≤ 800.
**Критерии готовности:**
- [ ] оба ≤ 800
- [ ] маршруты не изменились (drift-check pass)

---

### T1.1 — Завершить миграцию root-level tails под Core/
**Параметр:** 1 | **Приоритет:** P1 | **Зависит от:** T3.1 | **+Балл:** 4

**Файлы:** см. `docs/legacy_map.md` (текущие tails) + `docs/MODULAR_STRUCTURE.md`.

**Шаги:**
1. Read `docs/legacy_map.md` — список оставшихся tails.
2. Для каждого tail: переместить под `Core/` (или `CoreModules/` если
   переиспользуемый), обновить импорты, `pyproject.toml` pythonpath,
   `requirements-dev.txt`, `scripts/quality_gate.py` PYTHONPATH.
3. Обновить `docs/legacy_map.md` — убрать перенесённые, оставить только
   намеренно-legacy.
4. `PY_ROOT_GUARD` + `GATE_FULL`.
5. Bump версии + CHANGELOG.

**VERIFY:** `PY_ROOT_GUARD` pass; `GATE_FULL` pass; `docs/legacy_map.md`
актуален.
**Критерии готовности:**
- [ ] нет незадокументированных root-level runtime-пакетов

---

### T2.1 — Убрать импорты реализаций между CoreModules (только контракты/HTTP)
**Параметр:** 2 | **Приоритет:** P1 | **Зависит от:** T3.1 | **+Балл:** 3

**Файлы:** grep `from rag_service`, `from llm_proxy`, `from webui_backend`
между CoreModules (не из Core/).

**Шаги:**
1. Grep кросс-импорты реализаций между CoreModules (исключая `Core/core/`
   contracts).
2. Для каждого: заменить на HTTP-вызов или импорт из `Core/core/contracts/`.
3. Добавить import-linter контракт `modules_http_only` (forbidden: CoreModules
   → другой CoreModules implementation package; разрешить только
   `core`, `core.contracts`).
4. `lint-imports` + `GATE_FULL`.
5. Bump версии + CHANGELOG.

**VERIFY:** `lint-imports` pass (включая новый контракт); `GATE_FULL` pass.
**Критерии готовности:**
- [ ] CoreModules изолированы
- [ ] общаются через контракты/HTTP

---

### T1.2 — ADR для архитектурных решений
**Параметр:** 1 | **Приоритет:** P1 | **Зависит от:** — | **+Балл:** 4

**Файлы:** `docs/adr/` (СОЗДАТЬ) — `0001-layered-architecture.md`,
`0002-extension-system.md`, `0003-llm-proxy-compat.md`,
`0004-modular-migration.md`, `0005-docker-contract.md`.

**Шаги:**
1. Создать `docs/adr/0001-*.md` ... `0005-*.md` по шаблону ADR
   (Context, Decision, Consequences, Status).
2. Каждый ADR описывает принятое решение и его обоснование.
3. Bump версии + CHANGELOG.

**VERIFY:** 5 ADR-файлов существуют, валидный markdown.
**Критерии готовности:**
- [ ] ≥5 ADR

---

### T4.2 — Integration-набор полного RAG-pipeline
**Параметр:** 4 | **Приоритет:** P1 | **Зависит от:** T4.1 | **+Балл:** 4

**Файлы:** `tests/rag_service/test_rag_pipeline_integration.py` (СОЗДАТЬ).

**Шаги:**
1. Создать integration-тест: embed (mock) → search (mock Qdrant) → rerank
   (mock) → build_context_block → chat (mock provider) на фикстурах.
2. Маркер `@pytest.mark.integration` + `@pytest.mark.slow`.
3. Проверить, что pipeline проходит end-to-end с реальными сигнатурами
   (не только моки сигнатур, но и реальный flow).
4. Bump версии + CHANGELOG.

**VERIFY:** `pytest tests/rag_service/test_rag_pipeline_integration.py -q` pass.
**Критерии готовности:**
- [ ] integration-тест RAG-pipeline существует и проходит

---

### T4.3 — Property-based тесты для парсеров
**Параметр:** 4 | **Приоритет:** P1 | **Зависит от:** T4.1 | **+Балл:** 2

**Файлы:**
- `tests/domain/test_markdown_meta_property.py` (СОЗДАТЬ)
- `requirements-dev.txt` — добавить `hypothesis` в `[dev]`

**Шаги:**
1. Добавить `hypothesis` в `pyproject.toml` `[project.optional-dependencies].dev`.
2. Создать property-тесты для `parse_and_strip_meta_block`: idempotent strip,
   round-trip (parse → strip → re-parse = empty), пустой/некорректный ввод.
3. Bump версии + CHANGELOG.

**VERIFY:** `pytest tests/domain/test_markdown_meta_property.py -q` pass.
**Критерии готовности:**
- [ ] property-based тесты для парсеров

---

### T5.1 — Покрыть тестами вкладки CoreUI без тестов
**Параметр:** 5 | **Приоритет:** P1 | **Зависит от:** — | **+Балл:** 5

**Вкладки без тестов** (фактическое состояние):
`DevDocumentationTab.jsx`, `ExtensionRuntimeTab.jsx` (есть `.smoke.test.tsx`,
нужно полный), `ProxyJournalTab.jsx`, `ProxyTracesTab.jsx`,
`RagTesterV2Tab.jsx`, `TemplateEditorTab.jsx`, `CoreUIShowcaseTab.jsx`,
`CoreUIPillTabs.jsx`, `CoreUISubtabs.jsx`.

**Шаги (по одной вкладке = один коммит):**
1. Для каждой вкладки создать `<Name>.test.jsx` рядом (паттерн как
   `DashboardTab.test.jsx`): render, базовое взаимодействие, snapshot где
   уместно.
2. Использовать `@testing-library/react` (уже в devDeps).
3. После каждого: `UI_TEST` + `UI_BUILD`.
4. Bump версии + CHANGELOG (можно группировать по 2-3 вкладки).

**VERIFY:** `UI_TEST` pass; все целевые вкладки имеют `.test.*`.
**Критерии готовности:**
- [x] 0 вкладок без тестов (кроме намеренно-тривиальных)

---

### T5.2 — Порог покрытия CoreUI в CI
**Параметр:** 5 | **Приоритет:** P1 | **Зависит от:** T5.1 | **+Балл:** 3

**Файлы:**
- `CoreModules/CoreUI/package.json` — добавить `test:coverage`
- `CoreModules/CoreUI/vitest.config.*` — coverage threshold
- `scripts/quality_gate.py` — `coreui-coverage` шаг

**Шаги:**
1. Добавить `@vitest/coverage-v8` в devDeps (если нет).
2. Добавить script `"test:coverage": "vitest run --coverage"`.
3. Настроить coverage threshold в vitest config: lines 70%.
4. Добавить `GateStep("coreui-coverage", _npm_command("run", "test:coverage"), COREUI_ROOT, 180)` в FULL_GATE_EXTRA.
5. Bump версии + CHANGELOG.

**VERIFY:** `npm run test:coverage` pass (≥70%).
**Критерии готовности:**
- [x] coverage threshold 70% для CoreUI в CI

---

### T6.1 — Linux parity + matrix Python + кэш pip + coverage upload
**Параметр:** 6 | **Приоритет:** P1 | **Зависит от:** — | **+Балл:** 8

**Файлы:** `.github/workflows/quality.yml`.

**Шаги:**
1. Добавить `linux-full` job (ubuntu-latest) — полный `GATE_FULL` (не только
   fast-smoke), зеркальный `full` job.
2. В `setup-python` добавить `python-version` matrix: `["3.10","3.11","3.12","3.13"]`
   (минимум для minimal-gate; full — на 3.12).
3. `setup-python` уже имеет `cache: pip`? — добавить `cache: pip` +
   `cache-dependency-path: requirements-dev.txt` (или `**/pyproject.toml`).
4. Добавить step `codecov/codecov-action@v4` после pytest-full (нужен
   `--cov` + xml report).
5. Bump версии + CHANGELOG.

**VERIFY:** workflow YAML валиден (`python -c "import yaml; yaml.safe_load(open('.github/workflows/quality.yml'))"`).
**Критерии готовности:**
- [ ] linux-full job
- [ ] matrix 3.10-3.13
- [ ] кэш pip
- [ ] codecov

---

### T8.1 — SAST (bandit) + secret-scanning + Dependabot + CSP-аудит
**Параметр:** 8 | **Приоритет:** P1 | **Зависит от:** — | **+Балл:** 6

**Файлы:**
- `pyproject.toml` `[dev]` — добавить `bandit`, `gitleaks` (опц.)
- `scripts/quality_gate.py` — `bandit` шаг в FULL_GATE_EXTRA
- `.github/dependabot.yml` (СОЗДАТЬ)
- `Core/api/http/rag_routes.py` (или security middleware) — CSP headers

**Шаги:**
1. Добавить `bandit` в `[dev]`; добавить `GateStep("bandit", _python_command("-m", "bandit", "-r", "Core", "CoreModules", "-q"), REPO_ROOT, 120, required=False)` (advisory на старте).
2. Создать `.github/dependabot.yml`: ecosystem pip (weekly), npm
   (CoreModules/CoreUI, weekly), github-actions (monthly).
3. Добавить CSP + security headers в Flask app (X-Content-Type-Options,
   X-Frame-Options, Strict-Transport-Security, Content-Security-Policy).
4. Добавить gitleaks в CI (отдельный job или step).
5. Bump версии + CHANGELOG.

**VERIFY:** `python -m bandit -r Core CoreModules -q` → advisory (не падает
gate, но отчёт чистый или findings задокументированы).
**Критерии готовности:**
- [x] bandit advisory
- [x] dependabot
- [x] CSP headers
- [x] gitleaks

---

### T9.1 — Подпись манифестов + enforcement capabilities + тесты миграции
**Параметр:** 9 | **Приоритет:** P1 | **Зависит от:** — | **+Балл:** 6

**Файлы:**
- `extensions/bundled/*/chironai-extension.json` — поле `manifest_sha256`
- `CoreModules/ExtensionsHost/extensions_host/` — верификация
- `tests/extensions_backend/test_manifest_security.py` (СОЗДАТЬ/расширить)

**Шаги:**
1. Добавить опциональное поле `manifest_sha256` в контракт манифеста;
   ExtensionsHost проверяет хэш при установке (если присутствует).
2. Добавить тест: расширение не может вызвать capability, не заявленную в
   `capabilities` манифеста (enforcement).
3. Добавить тест миграции api_version (1 → 2): старый манифест
   rejected/предупреждён.
4. Bump версии + CHANGELOG.

**VERIFY:** `pytest tests/extensions_backend/ -q` pass.
**Критерии готовности:**
- [x] подпись манифестов
- [x] enforcement capabilities
- [x] тесты миграции

---

### T11.1 — Расширить ARCHITECTURE.md
**Параметр:** 11 | **Приоритет:** P1 | **Зависит от:** — | **+Балл:** 5

**Файлы:** `docs/ARCHITECTURE.md` (сейчас ~100 строк).

**Шаги:**
1. Расширить до ~300+ строк: полные слои с ответственностью, data flow
   (HTTP/CLI/RAG) с диаграммами mermaid, границы модулей, high-risk зоны
   (из AI_RULES секция 7), service control boundary, OpenAI compat policy.
2. Синхронизировать с фактическим состоянием (проверить пути через Grep).
3. Bump версии + CHANGELOG.

**VERIFY:** `docs/ARCHITECTURE.md` ≥ 300 строк; пути в тексте существуют
(выборочная проверка Grep).
**Критерии готовности:**
- [ ] ARCHITECTURE.md — полный источник истины

---

### T11.2 — README для каждого CoreModule
**Параметр:** 11 | **Приоритет:** P1 | **Зависит от:** — | **+Балл:** 4

**Файлы:** `CoreModules/*/README.md` — актуализировать (CoreUI сейчас 14
строк, DockerManager 5, LlmInteractor 2).

**Шаги:**
1. Для каждого CoreModule README: назначение, установка, ключевые
   импорты/entrypoints, как тестировать, зависимости.
2. CoreUI README: расширить (VITE_API_URL, dev/build/test команды, структура
   src/, токены, lazy-паттерн).
3. Bump версии + CHANGELOG.

**VERIFY:** все `CoreModules/*/README.md` ≥ 20 строк с разделами.
**Критерии готовности:**
- [x] каждый CoreModule имеет содержательный README

---

### T11.3 — CONTRIBUTING.md + onboarding-гайд
**Параметр:** 11 | **Приоритет:** P1 | **Зависит от:** T12.1 | **+Балл:** 3

**Файлы:** `docs/CONTRIBUTING.md` (СОЗДАТЬ), `docs/ONBOARDING.md` (СОЗДАТЬ).

**Шаги:**
1. `CONTRIBUTING.md`: ветки, Conventional Commits (из T12.1), PR-процесс,
   quality gate, version bump правило, AI_RULES-чеклист.
2. `ONBOARDING.md`: setup окружения, установка, первый PR, обзор архитектуры
   (ссылки на ARCHITECTURE.md + ADR).
3. Bump версии + CHANGELOG.

**VERIFY:** файлы существуют, валидный markdown.
**Критерии готовности:**
- [x] CONTRIBUTING + ONBOARDING

---

### T11.4 — Авто-генерация API-reference из OpenAPI
**Параметр:** 11 | **Приоритет:** P1 | **Зависит от:** T16.1 | **+Балл:** 3

**Файлы:** `scripts/gen_api_docs.py` (СОЗДАТЬ), `docs/api/` (СОЗДАТЬ).

**Шаги:**
1. Создать скрипт: build OpenAPI spec → рендер в markdown
   (через `widdershins` или ручной шаблонизатор) → `docs/api/reference.md`.
2. Добавить шаг в release-gate (advisory).
3. Bump версии + CHANGELOG.

**VERIFY:** `python scripts/gen_api_docs.py` → создаёт `docs/api/reference.md`.
**Критерии готовности:**
- [x] API-reference генерируется из spec

---

### T13.1 — Storybook + bundle budget + a11y + E2E
**Параметр:** 13 | **Приоритет:** P1 | **Зависит от:** T5.1 | **+Балл:** 6

**Файлы:**
- `CoreModules/CoreUI/.storybook/` (СОЗДАТЬ)
- `CoreModules/CoreUI/package.json` — storybook, axe-core, @playwright/test
- `CoreModules/CoreUI/scripts/bundle_budget.mjs` (СОЗДАТЬ)
- `CoreModules/CoreUI/e2e/` (СОЗДАТЬ)

**Шаги:**
1. Добавить Storybook (config + stories для CoreUI-примитивов:
   CoreUIButton, CoreUIPillTabs, CoreUISubtabs, CoreUIModal).
2. Добавить `bundle_budget.mjs`: проверка размера `dist/assets/*.js` против
   порога (текущий размер + 10% headroom); добавить в `coreui-build` или
   отдельный gate-шаг.
3. Добавить `axe-core` в vitest (a11y-тесты для ключевых вкладок).
4. Добавить Playwright E2E: RAG-запрос flow, управление расширениями
   (smoke, не полный coverage).
5. Bump версии + CHANGELOG.

**VERIFY:** `npm run storybook` (build) pass; `bundle_budget.mjs` pass;
a11y-тесты pass; E2E smoke pass.
**Критерии готовности:**
- [x] Storybook
- [x] bundle budget
- [x] a11y
- [x] E2E smoke

---

### T14.1 — Структурированные логи + Prometheus + OpenTelemetry + health-check
**Параметр:** 14 | **Приоритет:** P1 | **Зависит от:** — | **+Балл:** 6

**Файлы:**
- `Core/infrastructure/logging/` — JSON-логгер с correlation IDs
- `Core/api/http/health_routes.py` (СОЗДАТЬ) — `/health` с зависимостями
- `Core/api/http/metrics_routes.py` (СОЗДАТЬ) — `/metrics` (prometheus_client)
- `requirements-dev.txt` — `prometheus-client`, `opentelemetry-*` (опц.)

**Шаги:**
1. Структурированный JSON-логгер: каждый log-entry с `trace_id`,
   `request_id`, `module`.
2. `/health` эндпоинт: статус Qdrant, провайдеров, extension-runtime.
3. `/metrics`: request count/latency, RAG-pipeline длительность, ошибки.
4. OpenTelemetry spans для RAG-pipeline (embed/search/rerank/chat) — advisory.
5. Тесты для health + metrics.
6. Bump версии + CHANGELOG.

**VERIFY:** `pytest tests/api/ -k health -q` pass; `/health` и `/metrics`
возвращают 200 (через test client).
**Критерии готовности:**
- [x] structured logs
- [x] /health
- [x] /metrics
- [x] OTel spans

---

### T21.1 — Docker: trivy-скан + Ollama в compose
**Параметр:** 21 | **Приоритет:** P1 | **Зависит от:** — | **+Балл:** 3

**Файлы:** `docker-compose.yml` (добавить ollama), `.github/workflows/quality.yml`
(trivy step), `scripts/quality_gate.py` (trivy в release-gate).

**Шаги:**
1. Добавить `ollama` service в `docker-compose.yml` (image `ollama/ollama`,
   volume, healthcheck, `depends_on` в app).
2. Добавить trivy step в release job: `trivy image chironai:gate` (advisory
   на старте).
3. Bump версии + CHANGELOG.

**VERIFY:** `docker-compose config` валиден; trivy step в workflow.
**Критерии готовности:**
- [ ] ollama в compose
- [ ] trivy в release-gate

---

**ИТОГ ФАЗЫ 1: ~966 / 1000**

---

## 4. Задачи — Фаза 2 (P2, стратегические, ~+34 → 1000)

Фаза 2 требует организационных изменений (параметр 18) и долгосрочной
дисциплины. Параметр 18 — единственный, который ИИ-агент не может закрыть
полностью в одиночку (требует второго человека); агент может закрыть
документальную часть.

---

### T17.1 — Второй язык i18n (ru) + i18n-lint + workflow
**Параметр:** 17 | **Приоритет:** P2 | **Зависит от:** — | **+Балл:** 8

**Файлы:**
- `CoreModules/Localization/localization/catalog/ru/common.json` (СОЗДАТЬ)
- `CoreModules/CoreUI/src/services/i18n.js` — добавить `ru` в catalogs
- `CoreModules/CoreUI/scripts/i18n_lint.mjs` (СОЗДАТЬ)
- `CoreModules/Localization/localization/catalog.py` — registry локалей

**Шаги:**
1. Скопировать `en/common.json` → `ru/common.json`, перевести значения.
2. В `i18n.js` добавить `ru: ruCommon` в `catalogs`.
3. Создать `i18n_lint.mjs`: AST/regex-скан CoreUI `src/` на хардкод-строки вне
   `t()` (advisory); проверка полноты ключей (все ключи en есть в ru).
4. Добавить `i18n-lint` в `coreui-knip`-подобный gate-шаг (advisory).
5. Тест: отсутствие untranslated-ключей.
6. Bump версии + CHANGELOG.

**VERIFY:** `node scripts/i18n_lint.mjs` → 0 untranslated; `UI_BUILD` pass.
**Критерии готовности:**
- [ ] 2 языка
- [ ] i18n-lint
- [ ] полнота ключей проверена

---

### T18.1 — Документирование tribal knowledge (закрывает часть bus factor)
**Параметр:** 18 | **Приоритет:** P2 | **Зависит от:** T1.2 | **+Балл:** 10

> Это максимум, который ИИ-агент может дать параметру 18 без второго
> контрибьютора. Оставшиеся +12 требуют человека (см. T18.2).

**Файлы:**
- `docs/legacy_map.md` — актуализировать (tribal knowledge о хвостах)
- `docs/adr/` — дополнить (из T1.2)
- `docs/RUNBOOK.md` (СОЗДАТЬ) — инциденты, восстановление, диагностика
- `docs/ONBOARDING.md` — дополнить (из T11.3) walkthrough модулей
- `CoreModules/LogsManager/README.md` — расширить (tribal knowledge о
  proxy-journal)

**Шаги:**
1. `RUNBOOK.md`: процедуры для частых инцидентов (Qdrant недоступен,
   extension не стартует, proxy-ошибка, дрифт API), диагностика через
   LogsManager.
2. `legacy_map.md`: каждый tail — почему существует, когда убирается, кто
   владеет.
3. Walkthrough каждого CoreModule в ONBOARDING (входной поток, ключевые файлы,
   high-risk зоны).
4. Bump версии + CHANGELOG.

**VERIFY:** `docs/RUNBOOK.md` существует; `docs/legacy_map.md` актуален.
**Критерии готовности:**
- [ ] tribal knowledge задокументировано (закрывает +10 из +22)

---

### T18.2 — Второй контрибьютор (ОРГАНИЗАЦИОННО — не ИИ-задача)
**Параметр:** 18 | **Приоритет:** P2 | **Зависит от:** T18.1 | **+Балл:** 12

> **ВНИМАНИЕ:** эту задачу ИИ-агент НЕ может выполнить. Требует привлечения
> второго разработчика/ревьюера. Без неё максимум проекта = 988/1000
> (836 + 152 инженерно-закрываемых). Документ ниже должен явно отмечать этот
> потолок.

**Действия (для человека, не агента):**
- Привлечь второго контрибьютора / ревьюера.
- Включить branch protection: required review ≥1, required status checks.
- Кросс-ревью модулей, KT-сессии.

**VERIFY:** `git shortlog -sn --all` → ≥2 контрибьютора.
**Критерии готовности:**
- [ ] ≥2 контрибьютора
- [ ] branch protection включена

---

### T4.4 — Мутационное тестирование критичных сервисов
**Параметр:** 4 | **Приоритет:** P2 | **Зависит от:** T4.2 | **+Балл:** 2

**Файлы:** `pyproject.toml` `[dev]` — `mutmut` (или `cosmic-ray`).

**Шаги:**
1. Добавить `mutmut` в `[dev]`.
2. Настроить `mutmut config` на `Core/domain/services/` + `rag_service/domain/`.
3. Запустить baseline; задокументировать mutation score.
4. Bump версии + CHANGELOG.

**VERIFY:** `mutmut run` (advisory) → baseline задан.
**Критерии готовности:**
- [ ] мутационное тестирование настроено

---

### T7.3 — mypy в release-gate + vulture к нулю
**Параметр:** 7 | **Приоритет:** P2 | **Зависит от:** T7.2 | **+Балл:** 2

**Файлы:** `scripts/quality_gate.py` (RELEASE_TYPING_GATE), `pyproject.toml`
(`[tool.mypy]`), `mypy.ini`.

**Шаги:**
1. Добавить `mypy` в `[dev]`; настроить `[tool.mypy]` (relaxed для legacy,
   strict для domain/core).
2. Добавить `GateStep("mypy", _python_command("-m", "mypy", "Core/domain", "Core/core"), REPO_ROOT, 180)` в RELEASE_TYPING_GATE.
3. Свести vulture: для каждого finding — убрать мёртвый код или `# noqa: VXX
   <reason>`.
4. Bump версии + CHANGELOG.

**VERIFY:** `python -m mypy Core/domain Core/core` → exit 0; `PY_VULTURE` →
0 undocumented findings.
**Критерии готовности:**
- [ ] mypy в release-gate
- [ ] vulture чист

---

**ИТОГ ФАЗЫ 2: 1000 / 1000** (при условии T18.2 — второго контрибьютора).

---

## 5. Топологический порядок исполнения

Зависимости (выполнять слева направо, сверху вниз):

```
ФАЗА 0:
  T20.1 ─┬─> T20.3 ─> T20.4
         └─> T12.1 ─> T11.3
  T20.2 (независимо)
  T3.1 ──┬─> T1.1 (Ф1) ─> T2.1 (Ф1)
         └─> T1.2 (Ф1)
  T7.1 ──> T7.2 ──────────────────> T7.3 (Ф2)
  T10.1 ─┬─> T10.2
         └─> T16.1 ─> T11.4 (Ф1)
  T15.1 (независимо)
  T19.1 ─┬─> T19.2 (Ф1), T19.3 (Ф1), T19.4 (Ф1)
  T4.1 ──┬─> T4.2 (Ф1), T4.3 (Ф1) ─> T4.4 (Ф2)
         └─> T5.2 (Ф1)

ФАЗА 1 (после соответствующих P0):
  T1.1, T2.1, T1.2, T4.2, T4.3, T5.1 ─> T5.2, T6.1, T8.1, T9.1,
  T11.1, T11.2, T11.3, T11.4, T13.1, T14.1, T21.1, T19.2, T19.3, T19.4

ФАЗА 2 (после Ф1):
  T17.1, T18.1 ─> T18.2 (ЧЕЛОВЕК), T4.4, T7.3
```

---

## 6. Сводный gate после каждой фазы

### После Фазы 0
```
GATE_MINIMAL   # ruff, pytest-fast, collect, coreui-build, knip, lockfile, version-drift, api-drift
PY_IMPORTS     # ≥3 контракта
PY_OVERSIZED   # нет undocumented (oversized-files теперь required)
SMOKE          # build_and_run.bat
```
Ожидаемый балл: **886**.

### После Фазы 1
```
GATE_FULL      # + vulture, pytest-full, coverage-domain, coreui-coverage, bandit, mypy(опц)
PY_API_DRIFT   # strict
PY_ROOT_GUARD
UI_TEST        # все вкладки покрыты
SMOKE
```
Ожидаемый балл: **966**.

### После Фазы 2
```
GATE_FULL + RELEASE_GATE   # + mypy, trivy, dependency-audit
node CoreModules/CoreUI/scripts/i18n_lint.mjs   # 0 untranslated
git shortlog -sn --all   # ≥2 контрибьютора (T18.2 — человек)
```
Ожидаемый балл: **1000** (только при T18.2).

---

## 7. Потолок без второго контрибьютора

Если T18.2 не выполнена (нет второго контрибьютора), инженерно-достижимый
максимум:

```
836 (текущий)
+ 152 (все задачи кроме T18.2: +12)
= 988 / 1000
```

Параметр 18 (сопровождаемость/bus factor) остаётся на ~28/40. Это
**единственный параметр, который требует человеческого действия**, и он
должен быть явно отмечен в финальном отчёте агента как организационный блокер.

---

## 8. Чек-лист агента перед завершением каждой задачи

- [ ] Gate верификации задачи пройден (exit 0).
- [ ] Если менялся non-`.md` файл: version bump + CHANGELOG.
- [ ] Если менялся CoreUI `.jsx/.tsx`: `UI_BUILD` пройден, Showcase обновлён
      (если UI добавлен/удалён).
- [ ] Если менялся WebUI API: 4-точечная синхронизация
      (`webui_api.py` ↔ `api.js` ↔ Flask routes ↔ RESTX/OpenAPI).
- [ ] Если менялся import-контракт: `PY_IMPORTS` пройден.
- [ ] `PY_ROOT_GUARD` пройден (если трогал root-структуру).
- [ ] `SMOKE` (build_and_run.bat) пройден или причина явно указана.
- [ ] Не сломан публичный импортный контракт (при расщеплении файлов).
- [ ] Коммит содержит только изменения одной задачи.

---

## 9. Финальный отчёт агента (шаблон)

По завершении работы агент выводит:

```
WAY TO 1000 — ПРОГРЕСС
Фаза 0: X/N задач | +YY баллов | текущий ~ZZZ
Фаза 1: X/N задач | +YY баллов | текущий ~ZZZ
Фаза 2: X/N задач | +YY баллов | текущий ~ZZZ

БЛОКЕРЫ:
- T18.2 (второй контрибьютор) — ОРГАНИЗАЦИОННЫЙ, требует человека.
  Инженерный потолок без него: 988/1000.

НЕВЕРИФИЦИРОВАНО:
- <список gate, которые не удалось запустить, с причиной>
```

---

*Документ — исполняемый план для ИИ-агента. Все пути и команды основаны на
фактическом состоянии репозитория на момент составления. Перед каждой
задачей агент обязан сверяться с реальным состоянием файлов через
Read/Grep/Glob, не полагаясь на память.*
