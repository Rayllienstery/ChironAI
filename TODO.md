# ChironAI

## Быстрые заметки (из Notes)

- [ ] Auto start docker
- [ ] Esp 32 integration
- [ ] Fetch-update+build-run script
- [ ] Move scripts to the core folder
- [ ] Live session fix ui
- [ ] Unificate right bottom menu
- [ ] Tests summarized
- [ ] iPhone notifications
- [ ] Web framework search - work the same as crawl...

## Bugs
 - [ ] Proxy If RAG is not started the response is empty

---

## 0. Уже сделано в v0.2 (с учётом последних правок)

- **Переименование проекта**: проект переименован в **ChironAI** (обновлены README.md и TODO.md).
- **RAG‑лимиты для 20B**:
  - Уменьшен `RAG_CONTEXT_TOTAL_CHARS` до ~7k символов (раньше 10k+).
  - Уменьшен `RAG_TOP_K` до 4 (раньше 8) для снижения шума и повышения детерминизма.
- **Эмбеддинги**:
  - Добавлено ограничение длины текста для `/api/embed` и удаление блоков кода (```swift ... ```), чтобы не выбиваться за контекст модели эмбеддинга.
  - Улучшена обработка ошибок `/api/embed` (400, превышение контекста) с логированием подробностей.
- **Промпт / принципы**:
  - Усилен блок **RAG**: при наличии релевантных чанков (особенно с высоким score и подходящими версиями iOS/Swift) их **обязательно** нужно использовать и явно на них ссылаться.
  - Усилен запрет на выдуманные API (в т.ч. несуществующие сигнатуры типа `Observation.observe(...)`), явное разделение фактов из RAG и интерпретации.
  - Добавлены подробные принципы по Swift 6 strict concurrency, `@Observable`, `UIObservationTrackingEnabled`, UIKit + Observation (принцип 11), а также modular self‑check (Always, 2–5, 6–11).
  - Добавлено правило: если пользователь просит **«без кода»** — не выводить code‑blocks, только объяснение механики.
- **Детерминизм генерации**:
  - Вызовы Ollama /api/chat: выставлены `temperature = 0.0`, `top_p = 0.1` в `options`, что сильно снижает вариативность при фиксированном RAG‑контексте.
- **Логи RAG**:
  - Подробный лог найденных чанков: score, rerank_score, URL, doc_type, версии iOS/Swift, preview текста; это уже используется для анализа качества retrieval на сложных кейсах (Observation, Liquid Glass, Diffable + concurrency).

---

## 1. RAG (retrieval)

### 1.1 Гибридный поиск
- [x] **Qdrant hybrid** — добавить keyword/BM25 поиск по тем же чанкам (или по полю `text`), комбинировать с векторным (RRF или взвешенная сумма). Для точных запросов (имя API, версия) keyword часто бьёт лучше.
- [x] **Query expansion** — перед эмбеддингом генерировать 2-3 варианта запроса (синонимы, раскрытие аббревиатур: `@Observable` → `Observable macro`, `MVVM` → `Model View ViewModel`), искать по каждому, мержить результаты с дедупликацией.

### 1.2 Чанкинг и контекст
- [x] **Семантический чанкинг** — при индексации резать по границам секций/параграфов (заголовок + абзац), а не только по размеру; сохранять `section_path` в payload и при необходимости фильтровать по нему.
- [ ] **Лимиты контекста** — уже снижены (≈7k и topK=4) в коде; вынести `RAG_CONTEXT_CHUNK_CHARS`, `RAG_CONTEXT_TOTAL_CHARS`, `RAG_TOP_K` в конфиг/env и провести A/B‑тесты для разных моделей/размеров.
- [x] **Порог уверенности** — сделать `RAG_CONFIDENCE_THRESHOLD` настраиваемым; при низком score явно добавлять в системный блок фразу «Мало подходящих фрагментов» (уже частично есть — проверить единообразие).

### 1.3 Rerank
- [x] **Модель rerank** — в `rag_client.py` сейчас захардкожен `"model": "devstral-ios"` в `rerank()`. Вынести в env (например `RAG_RERANK_MODEL`) и использовать ту же модель, что и чат, или отдельную лёгкую.
- [ ] **Rerank по заголовкам** — опция: для rerank передавать только заголовки/первые строки чанков вместо 300 символов — меньше токенов, стабильнее порядок для мелкой модели.
- [x] **Fallback при сбое rerank** — при таймауте/невалидном JSON логировать и возвращать топ по векторному score + doc_type (уже есть возврат `hits` при ошибке — убедиться, что порядок осмысленный).

### 1.4 Concept Coverage (новый приоритетный слой)
- [ ] **Сместить цель retrieval: similarity -> coverage**
  - Трактовка: оптимизировать не только семантическую близость чанков, но и полноту ключевых концептов для ответа.
- [ ] **Добавить слой concept expansion после первого retrieval**
  - Трактовка: извлекать найденные концепты и расширять их связанными (например `actor -> Sendable, nonisolated, MainActor`), затем догружать вторичный контекст.
- [ ] **Ввести двухпроходный retrieval**
  - Трактовка: pass 1 находит тему, pass 2 добирает недостающие связанные концепты.
- [ ] **Добавить coverage gate перед финальной генерацией**
  - Трактовка: если `coverage < 0.75`, запускать расширение контекста и только потом финальный ответ.
- [ ] **Сделать targeted auto-retry при низком coverage**
  - Трактовка: retry не общий, а только с дозабором missing concepts и одной повторной генерацией.
- [ ] **Поднять `top_k` контролируемо**
  - Трактовка: увеличить recall (например до 15-20), но компенсировать шум через дедупликацию и фильтрацию.
- [ ] **Сжимать и структурировать контекст для LLM**
  - Трактовка: формировать компактные блоки `Concepts / Relations / Evidence`, чтобы снизить токены и улучшить связность.
- [ ] **Разделять типы FAIL: retrieval vs reasoning**
  - Трактовка: если `missing_concepts != []` — проблема retrieval; если coverage полный, но ответ провален — модель/reasoning.
- [ ] **Усилить prompt-контракт на полноту**
  - Трактовка: требовать покрытие критичных концептов без превращения ответа в жесткий "мертвый" шаблон.
- [ ] **Добавить диагностику по каждому запуску**
  - Трактовка: логировать found/missing concepts, coverage ratio, размер контекста и latency по этапам.
- [ ] **Считать GPU вторичной оптимизацией на текущем этапе**
  - Трактовка: сначала улучшать архитектуру retrieval/composition, затем масштабировать железо под throughput.
- [ ] **Вести A/B оценку на фиксированном наборе из 115 тестов**
  - Трактовка: измерять accuracy и latency после каждого изменения пайплайна, а не полагаться на субъективные ощущения.

---

## 2. Промпт

### 2.1 Содержание
- [x] **Версионирование промпта** — хранить промпты в `prompts/*.md`, подгружать при старте по имени (`rag.prompt` / `RAG_PROMPT`).  Реализовано; для воспроизводимости — версионировать изменения в Git; при необходимости вести CHANGELOG в `prompts/`.
- [x] **Два режима промптов: Swift 5 и Swift 6** — реализовать два варианта системного промпта (Swift 5 vs Swift 6), чтобы не путать систему: в одном — правила и принципы под Swift 5, в другом — под Swift 6 (strict concurrency, изоляция, Sendable и т.д.). Переключение режима — через WebUI (выбор в интерфейсе), чтобы пользователь явно указывал целевую версию языка.
- [ ] **A/B тесты** — возможность передавать вариант промпта через query param или header (например `X-Prompt-Variant: short`) для сравнения качества без деплоя.
- [x] **Явный запрет выдуманных API** — при отсутствии в RAG не генерировать конкретные сигнатуры (например `glassEffect(_:in:)`) без пометки «интерпретация»; при необходимости ужесточить формулировку в блоке «ДАННЫЕ ИЗ RAG».

---

## 3. Доступ в интернет (web search)

- [ ] **Условие вызова** — по ключевым словам («последняя версия», «latest», «current», «iOS 26», «когда вышла») вызывать веб-поиск (Bing/Google API, SerpAPI, Tavily и т.д.).
- [ ] **Интеграция в контекст** — результат поиска (1–3 сниппета или одна выдержка с URL) добавлять вторым блоком в системное сообщение после RAG: «Дополнительно из веб-поиска (на дату запроса): …». В промпте явно указать: этот блок только для актуальности дат/релизов; для API и кода приоритет — RAG.
- [ ] **Без смешивания** — не смешивать факты из RAG и из веба в одном утверждении; при конфликте указывать источник (RAG vs web).
- [ ] **Rag: web search for frameworks** — расширить условие вызова веб-поиска: если запрос явно про фреймворк/библиотеку (SwiftUI/Observation/UIKit и т.п.) и в RAG недостаточно/низкий confidence, добивать релевантной web-выдержкой по документации фреймворка; добавлять ее отдельным блоком и явно помечать как web-источник.
- [ ] **Конфиг** — API key и провайдер поиска вынести в env; при отсутствии ключа не вызывать поиск, работать только с RAG.

---

## 4. Модели и эмбеддинги

- [x] **Чат-модель** — в `rag_proxy.py` модель захардкожена; вынести в env (например `OLLAMA_CHAT_MODEL`) для смены без правки кода.
- [x] **Rerank-модель** — см. п. 1.3; вынести в env.

---

## 5. Тестирование и оценка качества

### 5.1 Регрессионные тесты
- [ ] **Набор эталонных запросов** — файл (JSON/YAML) с парами (запрос, ожидаемые ключевые факты/API или «нет в RAG»); скрипт запускает RAG + прокси, парсит ответ и проверяет наличие ключевых фраз или отсутствие запрещённых (force unwrap, русские комментарии в коде).
- [ ] **Интеграция с app_tester** — `app_tester.py` сейчас тестирует загрузку одной страницы; добавить сценарий: заданный URL → markdown → чанки → эмбеддинг → поиск по тестовому вопросу и проверка, что ожидаемый чанк в топ-N.

### 5.2 Бенчмарки
- [ ] **Латентность** — логировать время: RAG (embed + search + rerank), Ollama chat, полный запрос; выводить перцентили (p50, p95) при запуске тестовой пачки.
- [ ] **Качество retrieval** — для подмножества запросов вручную размеченные релевантные документы; считать Hit@K, MRR или точность «нужный чанк в топ-4».
- [ ] **Качество ответов** — экспертная разметка 20–30 ответов (правильность фактов, соблюдение структуры, отсутствие force unwrap / русских комментариев); зафиксировать baseline для v0.3 и повторять после изменений.

---

## 6. Наблюдаемость и эксплуатация

- [ ] **Метрики** — счётчики: число запросов, число запросов с пустым RAG, число с низким confidence; опционально экспорт в Prometheus/StatsD.
- [ ] **Логирование** — структурированные логи (JSON) с полями: query_hash, num_chunks, max_score, model, latency_ms, stream; для отладки и анализа.
- [ ] **Отдельный error‑логгер WebUI** — выделенный логгер для ошибок WebUI (например, `webui_errors.log`): HTTP‑ошибки, исключения при крауле/индексации, ошибки конфигов. Настроить ротацию логов и минимальный формат (timestamp, level, source, message, traceback_id).
- [ ] **Health check** — endpoint `GET /health`: проверка доступности Ollama и Qdrant; возвращать 503 при недоступности одного из них.
- [ ] **Конфиг** — единый конфиг (YAML/JSON или env): URL Ollama/Qdrant, имена моделей, лимиты RAG, порог confidence, включение веб-поиска.

---

## 7. Документация и структура проекта

- [ ] **README** — в корне проекта: назначение (ChironAI v0.3), требования (Python, Ollama, Qdrant), установка, запуск краулера и индексации, запуск прокси, настройка Zed; ссылки на TODO.md и CHANGELOG.
- [ ] **CHANGELOG** — версии 0.1, 0.2, 0.3 с перечнем изменений (промпт, RAG, принципы самопроверки, Liquid Glass и т.д.).
- [ ] **Описание промпта** — отдельный документ (например `docs/PROMPT.md`): структура ответа, блоки RAG/архитектура/самопроверка, принципы 1–10, когда применяются 2–5 и 10.
- [ ] **Дублирование app.py** — в корне есть `app.py` и в `WebUI/app.py`; уточнить, какой используется для краула/индексации, и при необходимости оставить один entry point с путями относительно корня/WebUI.

---

## 8. Качество кода (проект)

- [ ] **Типизация** — включить проверку типов (mypy или pyright) для `rag_proxy.py`, `rag_client.py`, ключевых функций в `app.py`; исправить замечания.
- [ ] **Русские комментарии** — в `rag_client.py` и других файлах часть комментариев на русском; по желанию перевести на английский для единообразия с промптом «код и комментарии на английском».
- [ ] **Тесты** — unit-тесты для `query_for_retrieval`, `_build_qdrant_filter`, `_framework_filter`, `_last_user_content` (все чистые функции); интеграционный тест: mock Ollama/Qdrant, POST /v1/chat/completions, проверка формата ответа и наличия RAG в системном сообщении.
- [x] **Rerank model** — убрать хардкод `devstral-ios` в `rag_client.rerank()`; читать из env.

---

## 9. Инфраструктура (опционально)

- [ ] **Docker** — Dockerfile для прокси (без краулера): Python, Flask, зависимости; опционально docker-compose с сервисами ollama, qdrant, rag-proxy для локального стенда.
- [ ] **Версионирование API** — если планируется несколько клиентов: префикс `/v1/` для chat completions и явная версия в ответе (уже есть `model: rag-ollama` — достаточно для v0.3).

---

## 10. WebUI для RAG Proxy

- [x] **WebUI-оболочка над прокси** — простое веб-приложение (отдельный фронтенд или шаблоны Flask) поверх `/v1/chat/completions` с:
  - переключателем **режима промпта (Swift 5 / Swift 6)** — выбор целевой версии языка, чтобы не смешивать правила Swift 5 и Swift 6 в одном промпте;
  - формой ввода запроса, выбора модели (если появятся), регулировкой `temperature`, `top_p`, `reasoning_level` и флага «только код»;
  - отображением RAG-чанков (score, rerank_score, URL, doc_type, версии iOS/Swift) для каждого запроса;
  - встроенным просмотром логов RAG-прокси (preview запросов/ответов, latency, статусы ошибок);
  - режимом «dev console» для дебага промпта и RAG без IDE (быстрые A/B тесты промпта и настроек генерации).
- [ ] **Settings: исключить некоторые Ollama-модели из списка** — добавить настройку в WebUI (например `hidden_models`/`exclude_models`), чтобы скрывать модели из выбора, не удаляя их из Ollama.

---

## Приоритеты для «радикального» скачка качества

1. **RAG:** гибридный поиск (vector + keyword), опционально query expansion; настраиваемые лимиты контекста и порог confidence.
2. **Веб-поиск:** выборочный вызов по запросу, отдельный блок в контексте, без смешивания с RAG-фактами.
3. **Тесты и метрики:** эталонные запросы + автоматическая проверка ответов; метрики латентности и RAG hit rate; health check.
4. **Конфиг и env:** все URL и имена моделей (чат, embed, rerank) в env/конфиге; версионирование промпта в файле.
5. **Документация:** README, CHANGELOG, описание промпта и принципов самопроверки.

После выполнения п. 1–2 и части п. 3–5 можно считать версию 0.4 с фокусом на «качество без смены модели».

---

## Post MVP

- [ ] **Локальные метрики качества RAG** — реализовать измерения Hit@K / MRR / «нужный чанк в топ-N» на основе эталонного набора запросов; считать распределение по моделям и конфигам, сохранять результаты в файл/БД для сравнения между версиями.
- [ ] **Автоматические проверки ответов** — добавить проверки на наличие запрещённых паттернов (force unwrap, выдуманные API, русские комментарии в коде, отсутствие ссылок на RAG-чанки при их наличии), падать тестами или помечать запрос как «failed».
- [ ] **A/B тестирование промптов** — возможность прогонять один и тот же набор запросов через разные варианты системного промпта (Swift 5 / Swift 6 / short / strict) и сравнивать метрики качества и количество ошибок.
- [ ] **Полу‑ручная экспертная оценка** — небольшой, но тщательно размеченный набор сложных запросов (Observation, Liquid Glass, сложные RAG‑кейсы), где эксперт вручную помечает правильность фактов, архитектурных рекомендаций и соблюдение принципов самопроверки.
- [ ] **AI-анализ тестовых запросов** — интеграция с внешним AI API (Anthropic/Claude или другой) для анализа тестовых запросов: кнопка в WebUI отправляет всю информацию о тестовом запросе (вопрос пользователя, найденные RAG-чанки, ответ модели, метрики) во внешний AI, который комментирует качество ответа, релевантность найденных чанков, соблюдение принципов и предлагает улучшения. Конфигурация API ключа через env, опциональное включение функции.

---

## 11. Senior iOS Assistant (Zed integration)

Цель этого блока — углубить манифест `SENIOR_IOS_ASSISTANT_MANIFEST.md` в реальный функционал проекта: отдельный режим ассистента уровня Senior iOS Dev с интеграцией в IDE (Zed).

### 11.1 Манифест и конфигурация

- [ ] **Подключить манифест в конфиг** — добавить ссылку на `SENIOR_IOS_ASSISTANT_MANIFEST.md` в документации (`README` или `docs/`), кратко описать, как этот режим отличается от обычного RAG‑чата.
- [ ] **Логическое имя модели** — в конфиге (`config/models.yaml` или новом YAML) ввести логическое имя профиля, например `senior-ios-assistant`, которое мапится на `rag-ollama` и конкретный Ollama‑chat‑модель.
- [ ] **Отдельный системный промпт** — завести отдельный Markdown‑промпт (например, `prompts/system_senior_ios_assistant_v1.md`), отражающий принципы из манифеста (роль Senior iOS Dev, акцент на архитектуре, конкурентности, тестируемости).
- [ ] **Режимы Swift 5 / Swift 6** — для Senior iOS Assistant явно поддержать выбор целевой версии Swift (см. TODO 2.1): либо через отдельные промпты, либо через параметр, прокидываемый в промпт.

### 11.2 Project analyzer

- [ ] **Zed: project analyzer** — реализовать сбор структурированного контекста по проекту (deployment target iOS, enabled frameworks/модули, признаки Swift 5 vs Swift 6, настройки конкурентности) и прокидывать это как input в Zed pre-prompt / system prompt.
- [ ] **Кэш и инвалидация** — кэшировать результаты анализа и обновлять только при изменениях релевантных файлов (чтобы не тормозить интерактивный IDE-поток).


### 11.3 Интеграция с Zed

- [ ] **Документация по интеграции** — в `README` (или отдельном `docs/ZED_INTEGRATION.md`) описать шаги подключения: URL `/v1/chat/completions`, логическое имя модели `senior-ios-assistant`, пример конфигурации Zed.
- [ ] **Контекст из файлов** — продумать, как Zed будет передавать в запрос путь/фрагмент файла (через system или user‑часть), и формализовать это в промпте (например: «Если в запросе присутствует путь к файлу и фрагмент кода — выполняй code review, а не общий ответ»).
- [ ] **Формат ответов для IDE** — договориться о формате: краткий summary + bullets с замечаниями + при необходимости фрагменты кода; добавить проверки в Rag Tests/скрипты, чтобы ответы выдерживали этот формат.

### 11.4 Метрики и обратная связь

- [ ] **Отдельные метрики режима Senior** — в логах/метриках помечать запросы, которые идут через профиль `senior-ios-assistant` (отдельный label); снимать латентность, hit‑rate RAG и процент успешных ответов по Rag Tests.
- [ ] **Экспертная валидация Senior‑ответов** — выбрать небольшой набор реальных кейсов (сложный SwiftUI экран, модуль со Swift Concurrency, архитектурный модуль) и периодически вручную оценивать ответы ассистента по шкале Senior/Middle/Junior.

### 11.5 Zed prompt pipeline (preview и детекторы)

- [ ] **Zed prompt preview** — показать пользователю в Zed сгенерированный (pre-)prompt перед отправкой запроса в `/v1/chat/completions` (минимум: выбранные версии Swift/iOS/platforms + основные блоки системного промпта).
- [ ] **Zed pre prompt: Swift version auto detector** — автоматически определять целевую версию Swift (5/6) по признакам в проекте/выбранном коде и передавать это в prompt variables.
- [ ] **Zed pre prompt: iOS version detector** — автоматически определять target iOS (deployment target / SDK-версию / доступность API) и передавать это в prompt variables с возможностью явного override.
- [ ] **Zed platforms detector** — определять target platform(s) (iOS/macOS/watchOS/tvOS) по проектным настройкам/импортам и использовать это для ограничений и формулировок в system prompt.
- [ ] **Prompt builder** — централизовать сборку системного промпта из: шаблона + результатов project analyzer + pre-prompt детекторов + правил самопроверки, чтобы переиспользовать один и тот же builder и для Zed, и для WebUI при необходимости.

### Cursor-like Zed Infrastructure (Apple/Xcode scope)

Цель: чтобы в Zed у ассистента был UX примерно как у Cursor (чат + IDE-контекст + preview/debug + агентные сценарии), но реализовано на нашей Apple-ориентированной RAG-инфраструктуре ChironAI.

Мэппинг Cursor фич -> Zed + ChironAI:

- [x] **Чат/мульти-турн в IDE** — реализовано форматом OpenAI-like `messages` в `/v1/chat/completions` (proxy для Zed: `api/http/rag_routes.py`).
- [x] **Режимы Swift 5 / Swift 6** — в system prompt через `get_rag_system_prompt_swift_mode()` и `swift_mode` в WebUI (и далее нужно прокидывать из Zed).
- [x] **RAG retrieval + подсказки из документации** — ядро pipeline: `build_system_content()` + `build_rag_context()` (domain/application layers) и показ RAG metadata в `include_rag_metadata`.
- [x] **Web search “для фреймворков” (на Apple scope)** — частично готово через `modules/external_docs_rag`:
  - триггеры/`on_demand_fetch`,
  - merged context с явной маркировкой блоков,
  - background refresh для коллекций при необходимости.
- [x] **Prompt preview / dev console** — полностью готово для WebUI (endpoint `webui_routes.py/tester/prompt-preview` + вывод `system_prompt_preview` в UI).
- [ ] **Prompt preview именно для Zed** — нужно расширить ответ proxy так, чтобы Zed получал `system_prompt_preview` (или отдельный endpoint).
- [ ] **Project-aware detectors (Swift/iOS/platform)** — сейчас есть version-heuristics “из текста запроса”, но нет анализатора Xcode project (`.xcodeproj`) для deployment target / swift language / enabled platforms.
- [ ] **Symbol search / find references / open snippet** — сейчас нет локального Swift symbol indexer и эндпоинтов для выдачи определений/сниппетов по AST.
- [ ] **Agent / tool workflows (Cursor-like)** — в текущем API нет поддержки `tool_calls` (OpenAI function calling протокол). Нужен либо server-side tool loop с формализованными tool-request/response, либо другой совместимый протокол.
- [ ] **Inline apply edits** — proxy сейчас возвращает только текст ответа; для Cursor-like “сразу применить изменения” нужен контракт формата diff/patch и/или отдельный apply-endpoint, который Zed сможет использовать.
- [x] **Настройки моделей/поведения прокси** — управляется в WebUI; дополнительно для Apple scope нужно унифицировать входные поля из Zed.

Далее — детальный план: что именно нужно сделать, какие артефакты/эндпоинты добавить и зачем (чтобы Zed-UX максимально повторял Cursor, но оставался в рамках Apple Ecosystem и нашей RAG-инфраструктуры ChironAI).

---

## Cursor-like Zed Infrastructure (Apple/Xcode scope) — доскональный TODO

### 0) Принципиальные ограничения (чтобы не строить невозможное)

- **Сейчас в `/v1/chat/completions` нет OpenAI-compatible `tool_calls` протокола** (поэтому “tool calling” Cursor-уровня нельзя включить флагом). Зачем: не тратить время на “магические” параметры, а сразу проектировать совместимый with-your-proxy формат.
- **Текущий proxy возвращает только текст ответа**, а “inline apply” требует отдельного контракта выдачи патчей и/или endpoint для apply. Зачем: Zed не сможет применить изменения, если мы не договоримся о формате.
- **Локальной symbol indexer / AST indexing в коде сейчас нет** — есть RAG по документации и внешнему контенту. Зачем: symbol-level navigation (find definition/references) требует отдельного индекса/эндпоинтов.

---

### 0.1) Xcode run/debug plugin для Apple scope (делаем первым, MVP)

Задача:

- Сделать “IDE-execution” слой для Apple Ecosystem scope: чтобы Zed (и/или внешний клиент) мог запускать и дебажить MacOS/iOS приложения так, как это делает Xcode:
  - выбор схемы (`scheme`),
  - выбор симулятора (`destination`: конкретное устройство/OS),
  - запуск/перезапуск,
  - получение статуса (build succeeded/failed, запуск/остановка),
  - и кнопка **“Open project in Xcode”** для переключения в полноценный отладчик Xcode.

Почему это “первым”:

- Cursor-UX в реальном проектировании почти всегда начинается с “сделай и запусти”, а потом дебажим.
- Даже идеальный RAG/символьный поиск не дает “операционную уверенность” без возможности быстро запустить схему/симулятор и увидеть результат/логи.

Что должно быть в MVP (минимально, но полноценно):

1) **Открытие проекта в Xcode**
  - Команда/endpoint, который по `workspace_root` и пути к `.xcodeproj/.xcworkspace` открывает Xcode на нужном проекте.
  - Зачем: быстрый escape hatch и переход в родной дебагger.

2) **Выбор scheme и destination**
  - Реализовать “enumeration”:
    - список доступных scheme’ов,
    - список доступных destinations (симуляторы/устройства) для выбранной конфигурации.
  - Зачем: без перечисления UI в Zed будет “слепым”.

3) **Run (build + launch)**
  - Минимально: вызвать `xcodebuild`/Xcode command-line в контексте выбранного scheme/destination и затем запустить приложение (для iOS через simulator).
  - Вывести:
    - build logs (обрезая/сворачивая),
    - итоговый статус,
    - идентификатор сессии запуска.
  - Зачем: Cursor-like “Run” должен быть наблюдаемым.

4) **Debug (минимально)**
  - MVP-вариант: запуск под дебагом через Xcode (то есть “debug request” открывает Xcode с нужной схемой/destination).
  - Более продвинутый вариант (позже): интеграция с LLDB/логами, если получится без тяжёлой разработки.
  - Зачем: корректный путь к дебагу даже если полноценная интерактивность появится позже.

5) **Cancel / Stop**
  - MVP: возможность отменить текущую build/run с безопасной остановкой процесса.
  - Зачем: управляемость.

---

Контракты и точки интеграции:

- **Где в архитектуре**: новый component уровня Infrastructure/Application (командная строка, процессы, управление симуляторами).
- **Как дергать из Zed**:
  - по отдельным HTTP endpoints прокси (например `/v1/ide/open-xcode`, `/v1/ide/run`, `/v1/ide/debug`, `/v1/ide/cancel`), либо
  - через будущий tool-loop (если появится совместимый протокол tool calls).

---

Engineering requirements (следующий спринт после MVP-плана):

- Какие поля нужны в запросах:
  - `scheme`,
  - `destination` (device + OS),
  - `configuration` (`Debug`/`Release`),
  - `workspace_path`/`project_path`,
  - опционально `derivedDataPath`, timeout’ы.
- Какие поля возвращать:
  - `status`,
  - `build_log_preview`,
  - `session_id`,
  - `exit_code` (если применимо).
- Ограничения:
  - read-only по проекту,
  - валидация путей, чтобы исключить запуск “не того” проекта.

### 0.1.b) SwiftPM Packages + DerivedData / Build management (дополнение к MVP)

Зачем (Cursor-like ожидание в Apple scope):
- После run/debug почти всегда нужно: обновить SwiftPM пакеты, почистить артефакты (DerivedData), посмотреть build outputs, затем “re-run/iterate”.
- Это сокращает время на “почему снова не запускается / почему не подхватились зависимости”.

A) SwiftPM Packages: подкачка/обновление + показ пакетов + показ контента

Задачи:
1) Discovery (что нужно анализировать):
  - найти `Package.resolved` и/или `Package.swift` (в контексте выбранного workspace/scheme),
  - опционально уточнять состав SPM через `.xcodeproj`/workspace context (если клиент передаст).
  - Зачем: показывать “реальность Xcode”, а не абстрактные догадки.

2) Actions (что должно уметь расширение):
  - `Fetch/Resolve Packages` (equivalent к Xcode “Resolve Package Versions” + fetch),
  - `Show Packages` (имя/версия если известна/статус: ok/fetching/failed),
  - `Show package content`:
    - минимум: targets/products (если извлекается),
    - желательно: краткое дерево ключевых файлов (например README/Documentation/CHANGELOG) + короткие preview.
  - Зачем: ассистенту и пользователю нужен быстрый контекст из пакетов без ручного открытия IDE.

3) Диагностика и UX:
  - progress states: resolving/fetching/done/failed,
  - `log_preview` stdout/stderr (коротко), плюс `log_id/session_id` для “полного лога”,
  - запрет/disable действий, если операция уже активна.

Контракты/точки интеграции (вариант через tool/endpoints; если позже появится tool-loop):
- `POST /v1/ide/spm/fetch`
  - request: `workspace_root`, `scheme?`, `configuration?`, `timeout?`
  - response: `status`, `log_preview`, `resolved_packages[]`, `updated_count?`
- `GET /v1/ide/spm/packages`
  - request: `workspace_root`, `scheme?`
  - response: `packages[]` (name, version?, status?)
- `GET /v1/ide/spm/package-content`
  - request: `workspace_root`, `package_id` + `path?` + `limit_chars?`
  - response: `files/tree` + `content_preview`

Ограничения:
- read-only по проекту (без правок исходников),
- безопасные таймауты и rate-limit на resolve/fetch,
- fail-closed при несовпадении workspace path (пакеты “только для выбранного проекта”).

B) DerivedData: открыть стандартную папку + Delete DD & Rebuild project

Задачи:
1) Определить стандартную папку DerivedData:
  - использовать Xcode default root, либо derivedDataPath если он был задан при запуске,
  - scope удаления — только project-specific derived data (fail-closed).

2) Actions:
  - `Open DerivedData folder`:
    - открыть Finder/проводник на DerivedData,
    - по возможности показать конкретные subfolders для проекта.
  - `Delete DD & Rebuild project`:
    - показать preview “что будет удалено”,
    - confirm (минимум для удаления),
    - удалить scope,
    - затем сделать rebuild в выбранной схеме/конфигурации,
    - вернуть:
      - `build status`,
      - `build_log_preview`,
      - `session_id`.

Контракты/эндпоинты (идея):
- `GET  /v1/ide/derived-data/path`
  - response: `derived_data_root`, `project_specific_paths[]`, `safe_deletion_scope[]`
- `POST /v1/ide/derived-data/open`
- `POST /v1/ide/derived-data/delete-and-rebuild`
  - request: `workspace_path`, `scheme`, `configuration`, `deletion_scope?`, `timeout?`
  - response: `status`, `deletion_preview`, `rebuild_session_id`, `build_log_preview`

Ограничения:
- “Delete” только в safe scope (валидировать что path соответствует текущему проекту),
- таймауты, защита от параллельных rebuild/delete,
- обязательные ошибки/сообщения при невозможности определить scope.

C) Clean project + Open build folder

Задачи:
1) `Clean project`:
  - выполнить Xcode clean для выбранного scheme/config,
  - вернуть `status` + `clean_log_preview`.

2) `Open build folder`:
  - открыть папку с build products/outputs для текущего scheme/config,
  - показать путь `build_folder_path` + минимум artifacts preview.

Контракты/эндпоинты (идея):
- `POST /v1/ide/project/clean`
- `POST /v1/ide/build/open-folder`

UI требования к плагину (MVP):
- единый блок “Build & Dependencies” с кнопками:
  - Fetch/Resolve Packages
  - Show Packages
  - Show package content
  - Open DerivedData folder
  - Delete DD & Rebuild project
  - Clean project
  - Open build folder
- state machine:
  - disable кнопок при активной операции,
  - progress + log preview,
  - понятные ошибки.

Тесты (что обязательно запланировать):
- Unit:
  - определение derived data paths (default vs custom),
  - формирование “safe deletion scope preview”,
  - построение команд/контрактов для clean/rebuild (без реального исполнения).
- Integration (с моками/фейк-исполнителем):
  - “delete-and-rebuild”: вызывает clean/build в правильной последовательности и возвращает session_id + log_preview,
  - “open-folder”: корректно возвращает path и не ломается на “derived data еще нет”.

### 0.2) Плагин для форматирования Swift после сохранения (Swift-Format / SwiftLint) — MVP

Задача:

- Сделать IDE-расширение (для Zed и/или Xcode-совместимого режима Apple scope), которое:
  - после каждого сохранения файла (on-save) запускает выбранный formatter/linter,
  - позволяет выбирать форматтер (например `Swift-Format`) и/или лентер (`SwiftLint`),
  - может устанавливать/обновлять инструменты (через extension UI: “Install/Update”),
  - применяет форматирование автоматически (если выбран режим format-on-save),
  - показывает результаты (ошибки/предупреждения) прямо в IDE без ручного копипаста.

Почему это “первым” (MVP-важность):

- Cursor-like UX “качество по умолчанию” обычно включает formatter + lint на save.
- Это уменьшает диффы, повышает компилируемость/стабильность рекомендаций и снижает шум от мелких стилевых нарушений.

MVP scope (что обязательно):

1) **Выбор инструмента**
  - `Swift-Format` (auto format)
  - `SwiftLint` (lint + диагностика)
  - Возможность выбрать режим: `format_on_save`, `lint_on_save`, `both`.
  - Зачем: пользователю нужен контроль, а не “всегда форматируй”.

2) **Установка/обновление**
  - Кнопки в UI expansion:
    - `Install Swift-Format`
    - `Install SwiftLint`
    - `Update Selected Tools`
  - При установке:
    - выбрать установочный метод (например Homebrew/standalone binaries) — если возможно в Apple scope,
    - сохранять “installed version” в конфиг/сессии.
  - Зачем: без установки extension бесполезен “из коробки”.

3) **Конфигурация**
  - Для `Swift-Format`:
    - путь к config (например `SwiftFormat.yml`) либо fallback на стандартный профиль.
  - Для `SwiftLint`:
    - чтение `.swiftlint.yml` из корня workspace,
    - fallback на дефолт если конфиг отсутствует.
  - Зачем: обеспечить воспроизводимость стиля проекта.

4) **Запуск на save (on-save hook)**
  - Гарантировать:
    - запуск только для `.swift` файлов (опционально `.swiftpm`/`.xcodeproj` не трогать),
    - дебаунс: не запускать форматтер 2-3 раза подряд при быстрых сохранениях.
  - Зачем: производительность и стабильность.

5) **Выдача результатов в IDE**
  - Для formatter:
    - показать “что изменилось” (diff preview) или применить молча (MVP может применить молча, но должен иметь preview toggle).
  - Для linter:
    - вывести ошибки/предупреждения как диагностики (file + line + message + rule id).
  - Зачем: без этого пользователь не увидит качество.

--- 

Контракты и точки интеграции (как вписать в нашу архитектуру):

1) Где должен жить “runner”
  - В идеале: отдельный component на стороне Zed/IDE для непосредственного запуска (если extension может запускать локальные команды).
  - Альтернатива: серверный endpoint в ChironAI proxy (например `/v1/ide/format` и `/v1/ide/lint`), где proxy вызывает инструменты локально и возвращает:
    - отформатированный текст или diff,
    - linter diagnostics.
  - Зачем: единый API для разных IDE клиентов.

2) JSON контракт (если идет через proxy)
  - Request:
    - `file_path`
    - `file_text` (опционально, если proxy не читает файл с диска)
    - `mode: "format" | "lint" | "both"`
    - `formatter: "swift-format" | null`
    - `linter: "swiftlint" | null`
  - Response:
    - `formatted_text` (если применимо)
    - `diff` или `patch` (опционально для preview)
    - `diagnostics: [{ line, column?, severity, rule, message, fix_available? }]`
    - `tool_versions` (для диагностики).

Ограничения:

- read-only безопасность:
  - если format-on-save должен изменять файл, это должно быть применением на стороне IDE (или строго ограниченное “write back”).
- производительность:
  - лимит времени на форматтер/линтер,
  - дебаунс и кэш результатов по `(file hash + tool versions + config hash)`.

---

План unit/integration tests (минимально для уверенности):

- Unit:
  - парсинг конфигов (если делаем на сервере),
  - парсинг вывода `swiftlint` в diagnostics (golden tests).
- Integration:
  - симуляция запуска runner на тестовом `.swift` файле (mock tool execution).


### 1) Cursor фичи, которые воспроизводим в Zed (Apple scope) — по блокам

#### 1.1 Чат в IDE с “идеальным контекстом” (чат + project aware)

Задачи:

- Определить и зафиксировать **Project Context Contract** в запросе к `/v1/chat/completions` (минимальный набор):
  - `project_context.swift_mode?: "swift5" | "swift6" | "default"`
  - `project_context.ios_versions?: string[]` (например `["18"]`)
  - `project_context.swift_versions?: string[]` (например `["6"]`)
  - `project_context.platforms?: string[]` (например `["iOS","macOS"]`)
  - `project_context.current_file?: string`
  - `project_context.selection?: string`
  - `project_context.frameworks?: list[{name:string}]` (под уже существующий механизм refresh коллекций)
  - Зачем: без формального контракта Zed будет присылать “что попало”, а наш prompt builder/retrieval не сможет быть детерминированным.
- В proxy (server-side) реализовать:
  - инъекцию `swift_mode` в system prompt (через `get_rag_system_prompt_swift_mode()`),
  - инъекцию IDE-блока (file/selection) в system prompt как “IDE PROVIDED CONTEXT (NOT RAG)”.
  - Зачем: это снижает галлюцинации (RAG факты не смешиваются с user code) и помогает модели давать локально релевантные правки.

Привязка к текущему коду:

- `api/http/rag_routes.py` уже принимает `project_context` как поле запроса, но сейчас фактически использует его только для `frameworks` (fresh/stale refresh коллекций).
- Prompt сборка существует: `config/rag_prompts.py` + `domain/services/prompt_builder.py` (`build_system_content()`).

#### 1.2 Prompt preview / dev console (аналог Cursor “show prompt / debug”)

Задачи:

- Добавить в `/v1/chat/completions` (proxy ответ) **`rag_metadata.system_prompt_preview`**:
  - preview должен включать: base system prompt + swift_mode header + IDE-блок (если есть) + маркер RAG блоков.
  - Зачем: Cursor требует “почему модель так ответила”; без системного preview отладка почти невозможна.
- Расширить логи/диагностику:
  - включить `project_context`-детали в dev console payload (что прислал IDE),
  - логировать `retrieval_question` (в embedding) — чтобы видеть “какие скрытые подсказки” использовались.
  - Зачем: это будет основой для regression тестов качества prompt pipeline.

Привязка:

- В WebUI уже есть preview в `/tester/prompt-preview` и поле `system_prompt_preview` в `rag_metadata` (для webui). Но для Zed-пути нужно то же самое на proxy-пути.

#### 1.3 RAG “web search for frameworks” (Cursor-like: автоподбор документации)

Задачи:

- Переподчинить поведение в Apple scope так, чтобы веб-факты добавлялись только:
  - когда вопрос “про фреймворк/библиотеку”,
  - и/или есть триггер “latest/current/версия”.
  - Зачем: “web search” превращается в управляемое расширение контекста, а не в хаотичное смешивание источников.
- Явно сделать “web block” вторым блоком в system prompt:
  - RAG block: только локальные фрагменты,
  - Web block: “fetched from web” + пометка источника,
  - правило конфликтов: “в одном утверждении не смешивать RAG и web факты”.
  - Зачем: снижает риски смешивания источников и помогает придерживаться ваших RAG truth rules.
- Использовать существующий модуль `modules/external_docs_rag`:
  - режим `on_demand_fetch`,
  - generic discovery (если фреймворк неизвестен — поиск в GitHub),
  - merged context.
  - Зачем: уже реализована большая часть “Cursor-like web research” без переписывания с нуля.

#### 1.4 Symbol-level navigation (Cursor “Go to definition / find references”)

Задачи:

- Добавить локальный **Swift symbol indexer** (AST-based target, эвристики как MVP-уровень).
  - MVP-вариант: index по regex/парсеру “сигнатур” (тип/функция/метод/extension) + хранение offset/snippet.
  - Target: AST parsing (SwiftSyntax) или иной стабильный парсер.
  - Зачем: без точной навигации Cursor не эмулируется, а RAG начинает “попадать в шумные куски”.
- Определить минимальный набор tool-like эндпоинтов для Zed:
  - `/v1/tools/search_symbols` — запрос имени символа + фильтры по module/platform
  - `/v1/tools/find_references` — symbol -> список ссылок (file+range)
  - `/v1/tools/open_file_snippet` — file+range -> snippet (размерный лимит)
  - Зачем: Zed сможет делать “операции над проектом”, а не только отвечать текстом.
- Добавить механизм индексации:
  - старт индексации “по требованию” (когда пользователь дергает symbol nav),
  - и инкрементальное обновление (watch mtime/хэш).
  - Зачем: индексация не должна тормозить интерактивный поток.

#### 1.5 Agentic workflows (Cursor “ask to do X”, multi-step)

Задачи:

- Так как tool_calls нет, проектировать **серверный “tool loop” протокол**:
  - модель должна возвращать строго формализованный JSON (например: `{ "tool": "...", "args": {...} }`),
  - proxy парсит JSON, вызывает соответствующие read-only функции (symbol search, rerank, web fetch, retrieval refresh),
  - затем делает повторный запрос модели с tool-results.
  - ограничить количество итераций (например 2-4) и фиксировать параметры.
  - Зачем: получить Cursor-like “agent” поведение без изменения Zed/OpenAI протоколов.
- Ввести tool-results “контекстные блоки”:
  - `TOOL RESULT: ...` как отдельный section в prompt,
  - запрет на запись в файлы (read-only).
  - Зачем: безопасность и предсказуемость.

#### 1.6 Inline apply edits (Cursor “apply patch”)

Задачи:

- Определить формат ответа, который Zed сможет применить:
  - вариант A: возвращать `unified diff` / `patch` в выделенном код-блоке,
  - вариант B: возвращать JSON с `files[]` и `diff` полями (если Zed это умеет),
  - вариант C: если Zed не умеет apply — только инструкции (fallback).
  - Зачем: “сразу применить изменения” требует общего протокола “diff generation + apply behavior”.
- Обновить системные правила (RAG truth rules + code/UI rules) так, чтобы:
  - при request “сделай изменения” модель возвращала diff,
  - запретить смешивать diff с обычным объяснением в одном блоке,
  - гарантировать “no placeholders / no TODO / compilable Swift”.
  - Зачем: Cursor-like inline edits должны быть напрямую применимыми.

#### 1.7 Настройки (Cursor “model/temp/context”)

Задачи:

- Нормализовать настройки входа из Zed в proxy:
  - `swift_mode` (если уже определено детектором, иначе default),
  - `reasoning_level` / `code_only` / `include_rag_metadata`,
  - ограничения: `temperature=0.0` для детерминизма.
  - Зачем: одинаковое поведение независимо от клиента.
- Добавить защиту от несовместимых сочетаний:
  - Swift 5 vs Swift 6 должны переключать нужные правила.
  - Зачем: иначе будет смешение моделей (и вы сами уже заложили Swift 5/6 mode как важный принцип).

---

### 2) Prompt pipeline для Apple scope (что именно будет происходить)

Единый pipeline (для Zed и (частично) для WebUI):

- Step 1: Собрать base system prompt из `prompts/<name>.md` (`config/rag_prompts.py`).
  - Зачем: версионирование промптов в Git и воспроизводимость.
- Step 2: Swift mode header (Swift 5/6) через `get_rag_system_prompt_swift_mode(prompt_name, swift_mode)`.
  - Зачем: строгое соблюдение strict concurrency / @Observable правил.
- Step 3: IDE context block (current_file + selection).
  - Формат: `IDE PROVIDED CONTEXT (user code/context; not RAG): ...`
  - Зачем: отделить “user code” от RAG facts.
- Step 4: Retrieval hints (скрытые подсказки для embedding/query).
  - Из `project_context.ios_versions / swift_versions / platforms` добавить версии/release tokens.
  - Зачем: поднять вероятность, что retrieval даст matching-варианты.
- Step 5: RAG context block:
  - собрать `chunks_info`, `max_score`, `confidence` и вставить в system.
  - при low confidence добавить caveat.
  - Зачем: соответствие RAG truth rules.
- Step 6: Web context block (опционально):
  - только когда включено и когда это релевантно (framework triggers / latest release).
  - Зачем: актуальные релизные изменения без смешивания источников.

---

### 3) Детекторы Apple/Xcode: что нужно анализировать и зачем

Цель: сделать “project aware” поведение Cursor-like — но в Apple scope.

#### 3.1 Xcode project analyzer (iOS + Xcode project scope)

Задачи:

- Реализовать парсинг `.xcodeproj/project.pbxproj`:
  - `deployment target` (для target’ов и конфигураций),
  - SDK / min iOS / conditional compilation flags,
  - Swift language mode (если доступно),
  - платформы (iOS/macOS/watch/tv) и active scheme.
  - Зачем: заменить “heuristics from query text” на реальную project truth.
- Опционально поддержать SPM артефакты:
  - `Package.swift`,
  - `Package.resolved` (dependencies/versions),
  - targets / products.
  - Зачем: помочь детектору frameworks и version pinning.
- Кэширование:
  - хранить результаты анализа и обновлять только при изменениях (workspace hash + mtimes).
  - Зачем: интерактивность.

#### 3.2 Swift version / concurrency detectors

Задачи:

- Swift version detector:
  - infer Swift 5 vs Swift 6 по признакам проекта (language mode, concurrency settings, use of @Observable и т.п.).
  - Зачем: чтобы подсказки и system prompt были консистентны.
- iOS version detector:
  - deployment target / SDK / платформенные availability markers.
  - Зачем: version-aware API selection в RAG и запрет “не существующих API”.
- Platforms detector:
  - определить целевые платформы и передать в prompt/retrieval constraints.
  - Зачем: чтобы модель не предлагала нецелевые платформенные API.

---

### 4) Symbol indexer (Swift) и endpoints

Задачи:

- Выбрать стратегию парсинга:
  - MVP: regex-based symbol extraction + snippet slicing,
  - Target: SwiftSyntax-based AST extraction.
  - Зачем: начать быстро, но сохранить траекторию к AST точности.
- Хранить индекс:
  - `symbols.json`/SQLite внутри проекта (или в кэше),
  - маппинг `symbol -> file+range+signature`.
  - Зачем: быстрый поисковый response для Zed.
- Реализовать endpoints:
  - search_symbols (query + filters),
  - find_references (symbol id -> references),
  - open_file_snippet (file path + range + max length).
  - Зачем: Cursor-like navigation.
- Инкрементальная индексация:
  - обновлять только измененные файлы.
  - Зачем: производительность.

---

### 5) Tool loop / agent loop протокол

Задачи:

- Определить tool schema:
  - tool name,
  - args validation,
  - error response.
  - Зачем: модель должна быть “строгой”, иначе loop сломается.
- Реализовать proxy-side dispatcher:
  - поддерживаемые tool’ы: retrieval refresh, rerank, symbol search, web fetch (on_demand), open snippet.
  - Зачем: все read-only.
- Инструментировать prompt для loop:
  - отдельные system правила: “return tool request JSON only”,
  - запрет текста вокруг JSON.
  - Зачем: parse reliability.
- Ограничения по итерациям:
  - max steps,
  - hard timeouts.
  - Зачем: стабильность и control cost.

---

### 5.0) Cursor-like “Plan first” + token-budgeting (ограниченный локальный LLM)

Проблема:

- Zed (или другой клиент) может использовать локальную LLM с ограничением по токенам.
- Если модель каждый раз получает полный chat history + большой RAG context, она не сможет ни составить план, ни выполнить его итеративно.

Цель:

- Чтобы Zed сначала строил компактный “plan”, а затем выполнял шаги так, чтобы:
  - каждый шаг помещался в token budget,
  - RAG context подбирался точечно под шаг,
  - старые данные сжимались в summary (а не отбрасывались полностью).

Задачи (что и зачем):

1) **Построение плана в компактном формате**
  - Ввести “Plan mode” контракт: модель возвращает только JSON/структуру плана (без длинных рассуждений).
  - Формат плана должен быть иерархическим:
    - Top-level: 3-6 шагов
    - Для каждого шага: цель, входные артефакты (какие поля context нужны), ожидаемые tool invocations (если tool loop используется), и критерий готовности.
  - Зачем: компактность + machine-readable план = меньше токенов и меньше ошибок.

2) **Итеративный план (hierarchical / rolling plan)**
  - Запретить “одним ответом” расписывать весь проект.
  - После выполнения шага обновлять plan:
    - либо сокращать оставшиеся шаги,
    - либо порождать новый mini-plan “на основании tool results”.
  - Зачем: локальный LLM не перегружается, а модель сохраняет актуальность.

3) **Token budget manager (серверный и/или клиентский)**
  - Определить token budget для трех частей:
    - план (plan JSON),
    - текущий шаг (step prompt),
    - summary (rolling memory).
  - При нехватке токенов:
    - сжимать summary,
    - уменьшать RAG context (top-N / context_total_chars),
    - приоритизировать:
      - IDE selection/current_file,
      - RAG chunks с наивысшим confidence/max_score,
      - chunks, относящиеся к текущему шагу.
  - Зачем: управляемость вместо “модель сама решит, что читать”.

4) **Суммаризация токенов (rolling summary)**
  - Добавить “сервис суммаризации контекста” (или логическую функцию в prompt pipeline):
    - summary(chat history) — короткий конспект решений/допущений/требований,
    - summary(ide context) — краткая фиксация того, что важно в selection/current_file,
    - summary(rag context) — суммаризация RAG chunks по шагам (не обязательно дословно, но с сохранением key-facts + ссылок/identifiers).
  - Зачем: старые подробности превращаются в компактную память.

5) **Шаг-ориентированная подборка RAG**
  - Для каждого шага плана формировать retrieval query на основе:
    - цели шага,
    - ожидаемых tool results (если есть),
    - project_context (swift_mode / platforms / ios_versions).
  - Ограничивать web/on_demand fetch только теми шагами, где это действительно нужно.
  - Зачем: “меньше, но точнее” — ключевой принцип работы с ограниченным LLM.

6) **Точки расширения в текущем коде (куда это логически вставлять)**
  - Prompt pipeline (system message сборка):
    - расширить `build_system_content()` / prompt builder так, чтобы вместо полного RAG контекста можно было вставлять “RAG summary by step”.
  - Retrieval query:
    - расширить `build_retrieval_query()` (у нас уже есть отдельные helper-логики) так, чтобы она учитывала `step_id`/`step_goal`.
  - API:
    - добавить поле в запрос/ответ (например `plan_mode` и `step_id`), чтобы proxy/пилот понимали:
      - на каком шаге мы находимся,
      - какую часть контекста сжимать.

---

### 6) Web search / framework docs UX (в Apple scope)

Задачи:

- Нормализовать триггеры:
  - “framework name in question”,
  - “latest/current”,
  - version constraints.
  - Зачем: web block должен быть предсказуем.
- Управляемые лимиты:
  - ограничить web context characters (например 50% от total),
  - лимит ссылок/фреймворков.
  - Зачем: контроль token budget.
- Визуализация источника:
  - помечать блок как “fetched from web”.
  - Зачем: RAG truth rule и диагностика.

Привязка к текущему коду:

- `modules/external_docs_rag` уже поддерживает `on_demand_fetch` и generic discovery, и собирает merged context.

---

### 7) Наблюдаемость (observability) и метрики Cursor-like уровня

Задачи:

- Сформировать “request timeline” для dev console:
  - input parsing -> project context detection -> prompt assembly -> RAG steps (embed/search/rerank/fetch/discovery) -> model call -> (optional) tool loop steps -> final response.
  - Зачем: “почему” в стиле Cursor.
- Метрики:
  - latency_total,
  - latency_rag_embed/search/rerank/fetch/discovery,
  - rag chunks count / max_score / confidence pass/fail,
  - tool loop step count.
  - Зачем: качество и регрессии.
- Хранить первые N фрагментов RAG:
  - чтобы UI/IDE мог показать их список.
  - Зачем: обучающий feedback.

---

### 8) Тесты и QA (чтобы план стал инженерным, а не “wish list”)

#### 8.1 Unit tests (детекторы/контракты/prompt assembly)

Задачи:

- Unit tests для Project Context Contract:
  - нормализация `swift_mode`,
  - сбор retrieval hints,
  - сбор IDE context block.
  - Зачем: контракт должен быть устойчив.
- Unit tests для prompt assembly:
  - swift 5/6 header inclusion,
  - правильная разметка RAG vs IDE vs Web blocks,
  - низкая confidence caveat.
  - Зачем: consistency с RAG truth rules.
- Unit tests для web search gating:
  - правильные триггеры,
  - корректные лимиты/обрезки.
  - Зачем: предотвратить “лишний web”.

#### 8.2 Integration tests (proxy + Zed contract)

Задачи:

- Интеграционный тест: `POST /v1/chat/completions`:
  - с `project_context` (swift_mode + platforms + selection),
  - с `include_rag_metadata=true`,
  - проверка что:
    - proxy добавляет IDE context в system preview,
    - retrieval hints влияют на запрос,
    - `rag_metadata` содержит ожидаемые поля (включая prompt preview).
  - Зачем: гарантировать что Zed integration не сломается.
- Интеграционный тест: web on-demand fetch merge (mock fetch client):
  - проверка “web block” присутствует и маркируется.
  - Зачем: контроль источников.

---

Но если смотреть холодно, следующий реальный апгрейд, который даст x10 качества:

reranker (bge-reranker / jina-reranker)

AST indexing для Swift

symbol search

tool calling

Без этого RAG почти всегда будет шумным.

#### Пояснение к апгрейду RAG

- **reranker** — отдельная модель (cross‑encoder), которая переупорядочивает top‑k результатов векторного поиска по релевантности к запросу и отбрасывает шумные фрагменты, чтобы в промпт попадали только максимально полезные куски.
- **AST indexing для Swift** — индексация не “сырого текста”, а AST Swift‑кода (типы, функции, свойства, связи), чтобы по запросам про конкретные сущности (`CommitViewModel`, `LoginUseCase`, `@Observable`‑модели) находить точные определения и связанные места использования.
- **symbol search** — поиск и навигация уровня IDE по символам (где определён тип/метод, где он используется), поверх AST‑индекса или отдельного индекса символов; позволяет RAG попадать в правильные файлы/функции, а не в случайные совпадения по тексту.
- **tool calling** — способность модели вызывать инструменты бекенда (`search_symbols`, `find_references`, `get_ast_node`, `open_file_snippet`, `rerank`) по ходу ответа, чтобы динамически доисследовать проект и собрать минимальный, но точный контекст, как это делает живой разработчик в IDE.
