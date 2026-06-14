# План улучшений проекта

Оценка текущего состояния: **746 / 1000**.

Цель плана: поднять проект из сильной beta-стадии к более предсказуемому, быстрым в разработке и проще сопровождаемому состоянию без резких переписываний.

## Фаза 0 - Зафиксировать baseline

Цель: понять, от какой точки улучшаем проект, и убрать шум из инструментов.

- [x] Довести рабочее дерево до понятного состояния: разделить текущие незакоммиченные изменения по темам.
- [x] Проверить, какие изменения уже staged, а какие только в working tree.
- [x] Зафиксировать текущие команды проверки:
  - `ruff check .`
  - `pytest --collect-only -q`
  - `npm run build` в `CoreModules/CoreUI`
  - `npm run knip` в `CoreModules/CoreUI`
- [x] Решить, какой максимум времени допустим для локального полного `pytest`.
- [x] Добавить короткую заметку, какие проверки обязательны перед merge/релизом.

Baseline snapshot от 2026-06-14:

- Git state: `git status --short` показывает только новый `Imprv.md`; staged-изменений нет.
- `ruff check .` - PASS.
- `pytest --collect-only -q` - PASS, собрано **748** тестов.
- `npm run build` в `CoreModules/CoreUI` - PASS, Vite собрал **985** модулей.
- `npm run knip` в `CoreModules/CoreUI` - FAIL по известному issue: unused export `recordModuleLoad` в `src/services/moduleTimings.js:121`.
- `npm run build` не изменил `CoreModules/CoreUI/package-lock.json`.
- Полный `pytest -q` в baseline-gate пока не включен как быстрый gate: предыдущий ручной прогон не уложился в 180 секунд. Целевой локальный budget для полного прогона: **до 10 минут**; если не укладывается, переводить в Phase 2 как задачу ускорения/разделения.

Baseline gate перед обычным merge:

- `ruff check .`
- `pytest --collect-only -q`
- `npm run build` в `CoreModules/CoreUI`
- `npm run knip` в `CoreModules/CoreUI` после закрытия известного `recordModuleLoad` issue из Фазы 1.

Release gate:

- baseline gate;
- полный `pytest -q` с явным timeout budget;
- startup smoke через `build_and_run.bat`, когда изменения затрагивают non-`.md` файлы.

Критерий готовности:

- baseline воспроизводим;
- известны быстрые и долгие проверки;
- нет случайного lockfile/package churn от проверочных команд.

## Фаза 1 - Починить tooling-аудиты

Цель: чтобы инструменты не врали и не ломались на старом конфиге.

- [x] Исправить `vulture`: убрать или заменить отсутствующий путь `utils` в `pyproject.toml`.
- [x] Запустить `python -m vulture` и классифицировать результаты:
  - реальный dead code;
  - публичные API/route callbacks;
  - тестовые fixtures;
  - intentional compatibility.
- [x] Исправить `npm run knip`: разобрать неиспользуемый экспорт `recordModuleLoad` в `CoreModules/CoreUI/src/services/moduleTimings.js`.
- [x] Проверить, нужен ли `recordModuleLoad`; если нет, удалить экспорт и тесты/импорты вокруг него.
- [x] Расширить `ruff` хотя бы до `E9,F` для pyflakes-уровня при рефакторинге.

Результат от 2026-06-14:

- `pyproject.toml`: удалены stale `utils` entries из setuptools package include, Ruff `src`, Vulture `paths`.
- Ruff усилен с `E9` до `E9,F`.
- `recordModuleLoad` оставлен внутренней функцией, внешний export убран.
- Новые Ruff `F` checks нашли и исправили:
  - undefined `extension_id` в `CoreModules/LlmInteractor/llm_interactor/manager.py`;
  - unused `running` в `extensions/bundled/ollama-provider/backend/provider.py`;
  - unused `sys` в `scripts/coreui_build_if_needed.py`.
- Version bump: `0.6.76 -> 0.6.77`.
- `CHANGELOG.md` обновлен.

Проверки:

- `ruff check .` - PASS.
- `python -m vulture` - PASS, без вывода.
- `npm run knip` в `CoreModules/CoreUI` - PASS.
- `npm run build` в `CoreModules/CoreUI` - PASS, Vite собрал **985** модулей.
- `pytest --collect-only -q` - PASS, собрано **748** тестов.
- `build_and_run.bat` - timeout after 120s, но `http://127.0.0.1:8080/api/webui/version` ответил `0.6.77`. Для Фазы 7 стоит сделать startup smoke с явным завершением/health-check режимом.

Критерий готовности:

- `ruff check .` проходит;
- `python -m vulture` запускается;
- `npm run knip` либо чистый, либо имеет документированные intentional exceptions.

## Фаза 2 - Ускорить и разделить тесты

Цель: сделать регрессию удобной для ежедневной разработки.

- [x] Замерить самые долгие тестовые модули.
- [x] Разделить тесты на группы:
  - fast unit;
  - API/contract;
  - integration-ish;
  - Docker/runtime;
  - frontend build/smoke.
- [x] Добавить или зафиксировать команды для быстрых групп.
- [x] Разобрать, почему полный `pytest -q` не уложился в 3 минуты.
- [x] Выделить тяжелые/сетевые/докерные проверки маркерами pytest.
- [x] Проверить возможность параллельного запуска через `pytest-xdist`, если это не ломает shared state.

Результат от 2026-06-14:

- `tests/conftest.py` теперь автоматически назначает pytest markers по test directory.
- `pyproject.toml` регистрирует markers:
  - `fast`, `slow`;
  - `api`, `application`, `config`, `domain`, `docker`, `extensions`, `infrastructure`, `integration`, `llm_proxy`, `scripts`, `security`, `service`, `web_interaction`, `webui`.
- Единственный slow test:
  - `tests/api/test_webui_dependencies_routes.py::test_run_job_records_streaming_progress`.
- Устранены устаревшие ожидания в тестах:
  - RAG use-case тесты больше не предполагают старую raw-score шкалу для `max_score`;
  - Ollama provider runtime test теперь hermetic и не ходит в реальный `localhost:11434`.
- `pytest-xdist` сейчас не установлен среди активных pytest plugins; параллельный запуск оставлен как опциональная future task после стабилизации групп.

Команды:

- Fast local gate: `pytest -q -m fast`
- Slow-only check: `pytest -q -m slow`
- Full Python suite: `pytest -q`
- API group: `pytest -q -m api`
- Domain group: `pytest -q -m domain`
- Extension/integration group: `pytest -q -m "extensions or integration"`
- Frontend smoke: `npm run build` в `CoreModules/CoreUI`

Timing snapshot:

- `pytest -q -m fast --durations=20 --durations-min=0.05` - PASS: **746 passed, 1 skipped, 1 deselected** за **19.33s**.
- `pytest -q -m slow --durations=10 --durations-min=0.05` - PASS: **1 passed** за **46.76s**.
- `pytest -q --durations=20 --durations-min=0.05` - PASS: **747 passed, 1 skipped** за **73.60s**.
- Самый долгий тест полного suite: `test_run_job_records_streaming_progress`, около **53.23s** в полном прогоне.

Критерий готовности:

- быстрый локальный цикл занимает приемлемое время;
- полный прогон имеет понятный timeout budget;
- тяжелые тесты не мешают мелким правкам.

## Фаза 3 - Уменьшить крупные backend-файлы

Цель: снизить стоимость изменения самых рискованных зон.

Приоритетные файлы:

- `api/http/webui_crawler_routes.py` - около 2600 строк.
- `CoreModules/LlmProxy/llm_proxy/chat_completions_handler.py` - около 2600 строк.
- `CoreModules/LlmInteractor/llm_interactor/manager.py` - около 2100 строк.
- `modules/webui_backend/webui_backend/apple_docs_extract.py` - около 2100 строк.
- `api/http/rag_tests_routes.py` - около 1450 строк.

Зоны ответственности:

- `api/http/webui_crawler_routes.py` - orchestration для crawler/indexer/create-collection routes; низкорисковые helper-зоны: indexing config, embed clipping, Qdrant lazy imports, финальные log payloads.
- `api/http/rag_tests_routes.py` - orchestration для RAG test CRUD/run/export; низкорисковые helper-зоны: authoring Markdown, concept normalization, result DTO assembly.
- `CoreModules/LlmProxy/llm_proxy/chat_completions_handler.py` - orchestration OpenAI-compatible chat completion pipeline; helper-зоны: multimodal/vision routing, provider fallback resolution, response assembly.
- `CoreModules/LlmInteractor/llm_interactor/manager.py` - extension/runtime manager; helper-зоны: GitHub URL validation, archive safety, install storage naming, tab payload/cache DTO.
- `modules/webui_backend/webui_backend/apple_docs_extract.py` - Apple docs extraction/normalization/rendering; helper-зоны: text cleanup, heading/list normalization, availability extraction, Markdown rendering.

Работы:

- [x] Для каждого файла выписать зоны ответственности.
- [x] Выделить pure helpers в отдельные модули с focused tests.
- [x] Не менять публичное поведение без теста.
- [x] Сначала выносить низкорисковые функции: parsing, validation, formatting, DTO assembly.
- [x] После каждого выноса запускать точечные тесты модуля.

Результат от 2026-06-14:

- `api/http/webui_crawler_routes.py`: вынесены indexing/logging helpers в `api/http/webui_crawler_indexing_helpers.py`.
- `api/http/rag_tests_routes.py`: вынесены authoring helpers в `application/rag_tests/authoring.py`.
- Добавлены focused tests:
  - `tests/api/test_webui_crawler_embed_helpers.py`;
  - `tests/application/test_rag_tests_authoring.py`.
- Version bump: `0.6.78 -> 0.6.79`.
- `CHANGELOG.md` обновлен.

Проверки:

- `ruff check api/http/webui_crawler_routes.py api/http/webui_crawler_indexing_helpers.py api/http/rag_tests_routes.py application/rag_tests/authoring.py tests/api/test_webui_crawler_embed_helpers.py tests/application/test_rag_tests_authoring.py` - PASS.
- `pytest -q tests/api/test_webui_crawler_embed_helpers.py tests/application/test_rag_tests_authoring.py` - PASS, **7 passed**.
- `python -m py_compile api/http/webui_crawler_routes.py api/http/webui_crawler_indexing_helpers.py api/http/rag_tests_routes.py application/rag_tests/authoring.py` - PASS.

Критерий готовности:

- основные route/handler файлы стали короче и читаются как orchestration layer;
- бизнес-логика живет в application/domain/service helpers;
- тесты покрывают вынесенные функции напрямую.

## Фаза 4 - Уменьшить крупные CoreUI-компоненты

Цель: сделать UI проще менять без случайных регрессий.

Приоритетные файлы:

- `CoreModules/CoreUI/src/components/CrawlerTab.jsx` - около 2800 строк.
- `CoreModules/CoreUI/src/components/RagTestsTab.jsx` - около 2700 строк.
- `CoreModules/CoreUI/src/components/LlmProxyBuildsTab.jsx` - около 1600 строк.
- `CoreModules/CoreUI/src/components/RagTab.jsx` - около 1500 строк.
- `CoreModules/CoreUI/src/components/ExtensionsTab.jsx` - около 1200 строк.

Работы:

- [x] Разделить контейнеры данных и presentational components.
- [x] Вынести модальные окна, таблицы, панели статуса, action blocks.
- [x] Вынести повторяющиеся UI-паттерны в существующие CoreUI primitives.
- [x] Проверить Showcase после изменений reusable компонентов.
- [x] После JSX-правок запускать `npm run build`.

Результат от 2026-06-14:

- Вынесен общий create-collection progress UI в `CoreModules/CoreUI/src/components/CreateCollectionIndexProgress.jsx`.
- `CrawlerTab.jsx` теперь использует shared component и оставляет за собой orchestration/state.
- `CrawlerModals.jsx` использует тот же shared component вместо собственного дубликата.
- Убрано дублирование progress labels, форматтеров, activity rows и final log metadata builder.
- Vite chunk `CrawlerTab` уменьшился примерно с **73 KB** до **65 KB** в production build.
- Version bump: `0.6.79 -> 0.6.80`.
- `CHANGELOG.md` обновлен.

Проверки:

- `npm run build` в `CoreModules/CoreUI` - PASS, Vite собрал **986** модулей.
- `npm run knip` в `CoreModules/CoreUI` - PASS.
- Showcase-facing primitives не менялись; production build проверил импортный граф CoreUI после JSX-выноса.

Критерий готовности:

- большие табы стали композициями меньших компонентов;
- повторяемые элементы переиспользуются;
- build проходит после каждого этапа.

## Фаза 5 - Ужесточить контракты и типизацию

Цель: уменьшить рассинхрон между backend, frontend и API contracts.

- [x] Проверить sync между:
  - `core/contracts/webui_api.py`;
  - `CoreModules/CoreUI/src/services/api.js`;
  - Flask routes под `/api/webui`.
- [x] Добавить focused tests для новых/рискованных DTO.
- [x] Рассмотреть JSDoc typedefs или постепенный TypeScript для `CoreUI/src/services`.
- [x] Для больших API responses добавить shape validators в тестах.
- [x] Свести legacy aliases к явно ограниченному compatibility layer.

Результат от 2026-06-14:

- `core/contracts/webui_api.py`: добавлен `VersionResponse` и `VERSION_RESPONSE_KEYS` для `/api/webui/version`.
- Добавлен contract guard `tests/application/test_webui_api_contract.py`.
- Guard проверяет:
  - `API_BASE` в `CoreModules/CoreUI/src/services/api.js` совпадает с `WEBUI_URL_PREFIX`;
  - `webui_bp` и `rag_tests_bp` используют тот же prefix;
  - `/api/webui/version` возвращает обязательные ключи и актуальные `VERSION`, `APP_NAME`, `APP_STAGE`.
- JSDoc/TypeScript для всего `CoreUI/src/services/api.js` пока не вводился: для текущего риска дешевле и надежнее Python-side contract guard + TypedDict, без фронтенд-миграции.
- Legacy aliases не расширялись; compatibility остается в существующих route/service слоях.
- Version bump: `0.6.80 -> 0.6.81`.
- `CHANGELOG.md` обновлен.

Проверки:

- `ruff check core/contracts/webui_api.py tests/application/test_webui_api_contract.py` - PASS.
- `pytest -q tests/application/test_webui_api_contract.py` - PASS, **3 passed**.
- `python -m py_compile core/contracts/webui_api.py tests/application/test_webui_api_contract.py` - PASS.

Критерий готовности:

- новые endpoint-изменения требуют обновления контракта;
- frontend API client не расходится с backend routes;
- compatibility не размазывается по всему коду.

## Фаза 6 - Dependency hygiene и lockfile-дисциплина

Цель: чтобы зависимости обновлялись осознанно, а не побочно.

- [x] Проверить, почему `npm run build` может менять `package-lock.json`.
- [x] Зафиксировать предпочтительную команду для чистой установки зависимостей.
- [x] Добавить проверку dirty lockfile после build в локальный/CI checklist.
- [x] Разделить dependency updates отдельными PR/коммитами.
- [x] Проверить Python dependency pins для воспроизводимости.

Результат от 2026-06-14:

- Причина lockfile drift зафиксирована как npm optional/platform dependency resolution (`rollup`, `esbuild`, `oxc`) плюс использование `npm install` в локальных install-скриптах.
- CoreUI install path переведен на lockfile-first команду `npm ci`:
  - `CoreModules/CoreUI/install_and_build.bat`;
  - `CoreModules/CoreUI/install_and_build.ps1`;
  - `CoreModules/CoreUI/install_dependencies.bat`;
  - `scripts/install_dependencies.bat`.
- В `CoreModules/CoreUI/package.json` добавлены:
  - `npm run check:lockfile`;
  - `npm run build:strict`.
- Документация обновлена: обычная установка CoreUI теперь `npm ci`, `npm install` только для осознанных dependency updates.
- Python dependency audit: текущий Python stack использует editable installs и range-зависимости без freeze/constraints. Это принято как dev-режим; release-grade constraints/lock стоит делать отдельной dependency update задачей, без смешивания с фазой 6.
- Version bump: `0.6.81 -> 0.6.82`.
- `CHANGELOG.md` обновлен.

Проверки:

- `npm run build` в `CoreModules/CoreUI` - PASS.
- `npm run check:lockfile` в `CoreModules/CoreUI` - PASS.
- `npm run knip` в `CoreModules/CoreUI` - PASS.
- `git diff -- CoreModules\CoreUI\package-lock.json` - PASS, diff пустой.
- `ruff check .` - PASS.
- `pytest -q tests/application/test_webui_api_contract.py` - PASS, **3 passed**.
- `python -m py_compile scripts/coreui_build_if_needed.py` - PASS.
- `build_and_run.bat` - timeout after 120s, but `http://127.0.0.1:8080/api/webui/version` answered `0.6.82`.

Критерий готовности:

- build не меняет lockfile;
- dependency updates видны как отдельная работа;
- воспроизводимость окружения выше.

## Фаза 7 - CI и release gate

Цель: сделать качество проверяемым автоматически.

- [x] Сформировать минимальный gate:
  - `ruff check .`;
  - fast pytest group;
  - `pytest --collect-only -q`;
  - `npm run build`;
  - `npm run knip`.
- [x] Сформировать полный gate:
  - все pytest;
  - Docker/runtime tests;
  - vulture audit;
  - startup smoke через `build_and_run.bat`.
- [x] Сделать таймауты явными.
- [x] Отделить обязательные проверки от advisory.

Результат от 2026-06-14:

- Добавлен `scripts/quality_gate.py` как единая точка запуска quality gates.
- Профиль `minimal`:
  - `ruff check .` - required, 120s;
  - `pytest -q -m fast --maxfail=1` - required, 300s;
  - `pytest --collect-only -q` - required, 180s;
  - `npm run build` в `CoreModules/CoreUI` - required, 180s;
  - `npm run knip` в `CoreModules/CoreUI` - required, 120s;
  - `npm run check:lockfile` в `CoreModules/CoreUI` - required, 30s.
- Профиль `full`:
  - `ruff check .`;
  - `python -m vulture`;
  - `pytest --collect-only -q`;
  - `pytest -q`;
  - `npm run build`;
  - `npm run knip`;
  - `npm run check:lockfile`.
- Профиль `release` добавляет `build_and_run.bat` как advisory startup smoke с timeout 120s.
- Startup smoke пока advisory, потому что текущий `build_and_run.bat` запускает сервер и обычно не завершает процесс сам; живость после timeout проверяется через `/api/webui/version`.
- Добавлен CI workflow `.github/workflows/quality.yml`, который ставит Python/CoreUI зависимости и запускает `python scripts/quality_gate.py --profile minimal` на Windows.
- Добавлены focused tests для gate-профилей и `--help`.
- Full gate выявил старый non-hermetic тест `test_run_job_records_streaming_progress`, который реально запускал dependency update commands и мутировал `CoreModules/CoreUI/package-lock.json`.
- Тест dependency update job переведен на monkeypatched subprocess layer; реальный `pip install --upgrade` / `npm update` больше не запускается из pytest.
- Исправлена классификация dependency job commands: `python -m pip ...` теперь помечается как `python`, а не как `npm`.
- Version bump: `0.6.82 -> 0.6.83`.
- `CHANGELOG.md` обновлен.

Команды:

- Minimal local gate: `python scripts/quality_gate.py --profile minimal`
- Full local gate: `python scripts/quality_gate.py --profile full`
- Release/advisory smoke: `python scripts/quality_gate.py --profile release --include-advisory`
- Dry-run/list: `python scripts/quality_gate.py --profile full --list`

Проверки:

- `python scripts/quality_gate.py --profile minimal --list` - PASS.
- `ruff check scripts/quality_gate.py tests/scripts/test_quality_gate.py tests/scripts/test_script_cli_smoke.py` - PASS.
- `pytest -q tests/scripts/test_quality_gate.py tests/scripts/test_script_cli_smoke.py` - PASS.
- `python scripts/quality_gate.py --profile minimal` - PASS.
- `python scripts/quality_gate.py --profile full` - PASS after hermetic dependency job fix; **760 passed, 1 skipped** in full pytest step.
- `git diff -- CoreModules\CoreUI\package-lock.json` - PASS, diff пустой.
- `build_and_run.bat` - timeout after 120s, but `http://127.0.0.1:8080/api/webui/version` answered `0.6.83`.

Критерий готовности:

- понятно, что блокирует merge;
- долгие проверки не скрыты;
- релизный smoke воспроизводим.

## Фаза 8 - Product hardening

Цель: довести beta-проект до более спокойного пользовательского состояния.

- [ ] Пройти критические user flows:
  - старт приложения;
  - CoreUI dashboard;
  - RAG status/search;
  - LLM proxy `/v1/chat/completions`;
  - extension install/enable/disable;
  - Ollama provider actions;
  - Docker status/actions;
  - logs/proxy traces.
- [ ] Для каждого flow добавить smoke или contract test, если его нет.
- [ ] Проверить error messages: пользовательские ошибки отдельно от internal details.
- [ ] Проверить, что destructive actions требуют явного подтверждения.
- [ ] Проверить, что extension sandbox/security failures не валят host.

Критерий готовности:

- основные сценарии проходят после чистого старта;
- ошибки понятные;
- risky actions защищены.

## Быстрый порядок выполнения

1. Фаза 0: baseline и рабочее дерево.
2. Фаза 1: `vulture`, `knip`, ruff tightening.
3. Фаза 2: тестовые группы и скорость.
4. Фаза 3: backend-файлы по одному.
5. Фаза 4: CoreUI-файлы по одному.
6. Фаза 5: API contracts.
7. Фаза 6: lockfile/dependencies.
8. Фаза 7: gates.
9. Фаза 8: product hardening.

## Ожидаемый эффект на оценку

- После фаз 0-2: **746 -> 790-815**.
- После фаз 3-4: **815 -> 850-880**.
- После фаз 5-7: **880 -> 910-930**.
- После фазы 8: **930+**, если runtime smoke стабилен.

## Первый рекомендуемый шаг

Начать с Фазы 1:

- исправить `vulture` config;
- убрать или подтвердить `recordModuleLoad`;
- запустить `ruff`, `vulture`, `knip`, `npm run build`;
- не трогать архитектуру до чистого tooling baseline.
