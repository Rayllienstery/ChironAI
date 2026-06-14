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

- [ ] Разделить контейнеры данных и presentational components.
- [ ] Вынести модальные окна, таблицы, панели статуса, action blocks.
- [ ] Вынести повторяющиеся UI-паттерны в существующие CoreUI primitives.
- [ ] Проверить Showcase после изменений reusable компонентов.
- [ ] После JSX-правок запускать `npm run build`.

Критерий готовности:

- большие табы стали композициями меньших компонентов;
- повторяемые элементы переиспользуются;
- build проходит после каждого этапа.

## Фаза 5 - Ужесточить контракты и типизацию

Цель: уменьшить рассинхрон между backend, frontend и API contracts.

- [ ] Проверить sync между:
  - `core/contracts/webui_api.py`;
  - `CoreModules/CoreUI/src/services/api.js`;
  - Flask routes под `/api/webui`.
- [ ] Добавить focused tests для новых/рискованных DTO.
- [ ] Рассмотреть JSDoc typedefs или постепенный TypeScript для `CoreUI/src/services`.
- [ ] Для больших API responses добавить shape validators в тестах.
- [ ] Свести legacy aliases к явно ограниченному compatibility layer.

Критерий готовности:

- новые endpoint-изменения требуют обновления контракта;
- frontend API client не расходится с backend routes;
- compatibility не размазывается по всему коду.

## Фаза 6 - Dependency hygiene и lockfile-дисциплина

Цель: чтобы зависимости обновлялись осознанно, а не побочно.

- [ ] Проверить, почему `npm run build` может менять `package-lock.json`.
- [ ] Зафиксировать предпочтительную команду для чистой установки зависимостей.
- [ ] Добавить проверку dirty lockfile после build в локальный/CI checklist.
- [ ] Разделить dependency updates отдельными PR/коммитами.
- [ ] Проверить Python dependency pins для воспроизводимости.

Критерий готовности:

- build не меняет lockfile;
- dependency updates видны как отдельная работа;
- воспроизводимость окружения выше.

## Фаза 7 - CI и release gate

Цель: сделать качество проверяемым автоматически.

- [ ] Сформировать минимальный gate:
  - `ruff check .`;
  - fast pytest group;
  - `pytest --collect-only -q`;
  - `npm run build`;
  - `npm run knip`.
- [ ] Сформировать полный gate:
  - все pytest;
  - Docker/runtime tests;
  - vulture audit;
  - startup smoke через `build_and_run.bat`.
- [ ] Сделать таймауты явными.
- [ ] Отделить обязательные проверки от advisory.

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
