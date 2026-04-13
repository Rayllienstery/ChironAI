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

- [ ] Check RAG Quality TASK
- [x] Autocomplete model inside proxy
- [ ] Crawler / Indexer - улучшить понимание того что было проиндексировано, а что нет - Indexed is ok, but skipped count is mandatory
- [ ] Indexing debug - why so much <400 chars filtering, probably it is useful files
- [ ] Indexing debug - Embedding failed: 3
Recent errors (3)
Failed to get embeddings for apple_documentation/visionos-a1eb03fc.md: 500 Server Error: Internal Server Error for url: http://localhost:11434/api/embed
Failed to get embeddings for apple_documentation/menustyle-18306f84.md: 500 Server Error: Internal Server Error for url: http://localhost:11434/api/embed
Failed to get embeddings for wwdc_sessions_2019_plus/wwdc2023-10241-transcript-eng-json-1bc00f62.md: 500 Server Error: Internal Server Error for url: http://localhost:11434/api/embed


## Bugs
 - [x] Proxy If RAG is not started the response is empty

## 1. RAG (retrieval)

### 1.2 Чанкинг и контекст
- [x] **Семантический чанкинг** — при индексации резать по границам секций/параграфов (заголовок + абзац), а не только по размеру; сохранять `section_path` в payload и при необходимости фильтровать по нему.
- [x] **Лимиты контекста (config/env)** — `RAG_CONTEXT_CHUNK_CHARS`, `RAG_CONTEXT_TOTAL_CHARS`, `RAG_TOP_K` вынесены в `config` / env (`config/__init__.py`, `config/README.md`, `rag.yaml` / `retrieval.yaml`).
- [ ] **A/B‑тесты лимитов контекста** — сравнение качества для разных моделей и размеров контекста после фиксации базовых лимитов.
- [x] **Порог уверенности** — сделать `RAG_CONFIDENCE_THRESHOLD` настраиваемым; при низком score явно добавлять в системный блок фразу «Мало подходящих фрагментов» (уже частично есть — проверить единообразие).

### 1.4 Concept Coverage (новый приоритетный слой)
- [x] **Сместить цель retrieval: similarity -> coverage**
  - Трактовка: оптимизировать не только семантическую близость чанков, но и полноту ключевых концептов для ответа.
  - Сделано: после rerank — опциональный отбор по покрытию концептов (`coverage_aware_selection` в `retrieval.yaml`, по умолчанию off): `extract_target_concepts_for_coverage` / `select_hits_for_concept_coverage` в `domain/services/retrieval.py`, `_finalize_reranked_hits` в `application/rag/use_cases.py`, усилен `build_rerank_prompt` (`domain/services/rerank.py`), описание в `config/README.md`.
- [x] **Слой concept expansion после первого retrieval**
  - Реализовано: `concept_expansion_enabled`, `concept_expansion_map`, семена из вопроса и топовых hit’ов pass 1, лимиты в `config/retrieval.yaml`; `expand_concepts_with_map` / `build_secondary_retrieval_query` в `domain/services/retrieval.py`; слияние и дедуп в `application/rag/use_cases.py`; описание в `config/README.md`.
- [x] **Двухпроходный retrieval**
  - Реализовано: pass 1 (embed + Qdrant), при включённом expansion — pass 2 (второй embed + поиск), merge уникальных hit’ов; тайминги и флаги в trace (`concept_expansion_pass2_*`).
- [x] **Coverage gate перед финальной генерацией**
  - Сделано: `coverage_gate_enabled`, `coverage_gate_min_percent`, `coverage_gate_boost_final_k`, `coverage_gate_max_final_k` в `retrieval.yaml`; при извлечённых целях и `coverage_ratio` ниже порога — один раз увеличить `final_k` из уже отранжированного пула (`build_rag_context` в `application/rag/use_cases.py`); флаг в таймингах / detail trace.
- [x] **Targeted retry при низком coverage (retrieval-слой)**
  - Сделано: `coverage_retry_supplemental_search_enabled` — доп. embed+search по запросу с missing terms, merge в пул, повторный rerank и finalize (`retrieval.yaml`, `use_cases.py`). Отдельный второй вызов chat completion не делался — один проход к модели с улучшенным контекстом.
- [x] **Поднять `top_k` / глубину контекста контролируемо**
  - Сделано: по-прежнему `top_k`, `multi_chunk_*`, `final_context_k`, pass2 и т.д. в YAML; плюс адаптивное расширение `final_k` через coverage gate и опциональный supplemental search.
- [x] **Структурировать контекст для LLM (опционально)**
  - Сделано: `structured_rag_context_enabled` — блоки Concepts / Evidence и нумерация `[n]` в `build_context_block` (`domain/services/prompt_builder.py` + зеркало в RagService); отдельный блок Relations не вводился (при необходимости — следующий шаг).
- [x] **Разделять типы FAIL: retrieval vs reasoning (частично)**
  - Сделано: `rag_metadata.rag_quality` с `failure_class`: `retrieval_gap` при непустых `missing_concepts` в отчёте покрытия, иначе `ok` при наличии целей; structured log `rag_request_completed` — `rag_quality`, `coverage_ratio`. Классификация «ответ модели плох при полном coverage» по-прежнему без автоматики.
- [x] **Усилить prompt-контракт на полноту / пробелы retrieval**
  - Сделано: заметка в system message при `missing_concepts` (`build_system_content`), дополнения в `RAG_SYSTEM_PREFIX` (`config/rag_prompts.py`), файл `prompts/system_rag_v1.md`.
- [x] **Диагностика по каждому запуску (базовый слой)**
  - Сделано: `rag_metadata.rag_trace` + **`coverage_report`** (targets / covered / missing / `coverage_ratio`) + **`rag_quality`** в прокси / webui / rag_service; в trace context assembly — краткий суффикс (coverage, gate_widen, retry_search); CoreUI: таймлайн, зеркало, карта конвейера на RAG / Qdrant.
  - Дальше по желанию: явный слой «reasoning fail», Relations в структурированном контексте, второй chat при экстремально низком coverage.

---

## 2. Промпт

### 2.1 Содержание
- [x] **Версионирование промпта** — хранить промпты в `prompts/*.md`, подгружать при старте по имени (`rag.prompt` / `RAG_PROMPT`).  Реализовано; для воспроизводимости — версионировать изменения в Git; при необходимости вести CHANGELOG в `prompts/`.
- [x] **Два режима промптов: Swift 5 и Swift 6** — реализовать два варианта системного промпта (Swift 5 vs Swift 6), чтобы не путать систему: в одном — правила и принципы под Swift 5, в другом — под Swift 6 (strict concurrency, изоляция, Sendable и т.д.). Переключение режима — через WebUI (выбор в интерфейсе), чтобы пользователь явно указывал целевую версию языка.
- [ ] **A/B тесты** — возможность передавать вариант промпта через query param или header (например `X-Prompt-Variant: short`) для сравнения качества без деплоя.
- [x] **Явный запрет выдуманных API** — при отсутствии в RAG не генерировать конкретные сигнатуры (например `glassEffect(_:in:)`) без пометки «интерпретация»; при необходимости ужесточить формулировку в блоке «ДАННЫЕ ИЗ RAG».

## 4. Модели и эмбеддинги

- [x] **Чат-модель** — в `rag_proxy.py` модель захардкожена; вынести в env (например `OLLAMA_CHAT_MODEL`) для смены без правки кода.
- [x] **Rerank-модель** — см. п. 1.3; вынести в env.

---

## 5. Тестирование и оценка качества

### 5.1 Регрессионные тесты
- [x] **Формализованные RAG-сценарии** — каталог `rag_tests/*.md` (вопрос, ожидаемые концепты, опции RAG Strict и т.д.), раннер `python -m api.cli rag-tests run` (см. `rag_tests/README.md`).
- [ ] **Эталонный набор в JSON/YAML** — отдельный файл с парами (запрос, ожидаемые ключевые факты/API или «нет в RAG») и скрипт с парсингом ответа под те же проверки, что в пункте выше (дублирование формата с markdown-тестами по желанию).
- [ ] **Интеграция с app_tester** — `app_tester.py` сейчас тестирует загрузку одной страницы; добавить сценарий: заданный URL → markdown → чанки → эмбеддинг → поиск по тестовому вопросу и проверка, что ожидаемый чанк в топ-N.

### 5.2 Бенчмарки
- [ ] **Латентность** — логировать время: RAG (embed + search + rerank), Ollama chat, полный запрос; выводить перцентили (p50, p95) при запуске тестовой пачки.
- [ ] **Качество retrieval** — для подмножества запросов вручную размеченные релевантные документы; считать Hit@K, MRR или точность «нужный чанк в топ-4».
- [ ] **Качество ответов** — экспертная разметка 20–30 ответов (правильность фактов, соблюдение структуры, отсутствие force unwrap / русских комментариев); зафиксировать baseline для v0.3 и повторять после изменений.

---

## 6. Наблюдаемость и эксплуатация

- [x] **Метрики (in-memory)** — счётчики и гистограммы в LLM Proxy: `rag_requests_total`, `rag_empty_results`, `rag_low_confidence`, latency/tokens и др. (`infrastructure/metrics`, запись из `CoreModules/LlmProxy/llm_proxy/chat_completions.py`).
- [ ] **Экспорт метрик** — выгрузка в Prometheus/StatsD или отдельный `GET /metrics` (сейчас только in-memory collector).
- [x] **Логирование (structured, proxy)** — JSON-строка `event: rag_request_completed` с `query_hash`, `chunks_count`, `max_score`, `model`, `latency_ms`, `stream`, шагами RAG (`rag_steps`); см. `_rag_request_completed_payload` в `chat_completions.py`.
- [x] **Отдельный error‑логгер WebUI** — `infrastructure/logging/webui_error_logger.py`: файл `webui_errors.log`, ротация, опционально JSON Lines (`LOG_FORMAT=json`); вызовы `log_webui_error` из прокси/WebUI.
- [x] **Health check** — `GET /health` в основном приложении (`api/http/rag_routes.py`), build proxy (`api/http/build_proxy_app.py`), standalone `rag_service` (`CoreModules/RagService/rag_service/api/http.py`); пробы Ollama `/api/tags` и Qdrant `/collections` через `infrastructure/stack_health.py`, при сбое — `503`.
- [ ] **Health: probe `/api/embed`** — опционально добавить проверку эмбеддинга (см. чеклист в `Improvement.md` §6.1).
- [x] **Конфиг** — YAML в `config/*.yaml` плюс env overrides (URL Ollama/Qdrant, модели, лимиты RAG, confidence, веб-поиск и т.д.; см. `config/__init__.py`, `config/README.md`).

---

## 7. Документация и структура проекта

- [ ] **README** — в корне проекта: назначение (ChironAI v0.3), требования (Python, Ollama, Qdrant), установка, запуск краулера и индексации, запуск прокси, настройка Zed; ссылки на TODO.md и CHANGELOG.
- [ ] **CHANGELOG** — версии 0.1, 0.2, 0.3 с перечнем изменений (промпт, RAG, принципы самопроверки, Liquid Glass и т.д.).
- [ ] **Описание промпта** — отдельный документ (например `docs/PROMPT.md`): структура ответа, блоки RAG/архитектура/самопроверка, принципы 1–10, когда применяются 2–5 и 10.
- [x] **Дублирование app.py** — отдельного `app.py` в корне репозитория нет; краул и индексация идут через [`WebUI/app.py`](WebUI/app.py) (см. CLI/README).
- [x] **.gitignore: DB / logs / secrets** — в корневом `.gitignore` уже есть `.env*`, ключи, `*.db`/`*.sqlite*`, `logs/`, `*.log`, кэши, дампы и др.; периодически перепроверять, что новые артефакты не утекают в коммиты.

---

## 8. Качество кода (проект)

- [ ] **Типизация** — включить проверку типов (mypy или pyright) для `rag_proxy.py`, `rag_client.py`, ключевых функций в `app.py`; исправить замечания.
- [ ] **Русские комментарии** — в `rag_client.py` и других файлах часть комментариев на русском; по желанию перевести на английский для единообразия с промптом «код и комментарии на английском».
- [x] **Тесты (retrieval / prompt helpers)** — `query_for_retrieval`, `build_qdrant_filter` / `merge_qdrant_filters`, `framework_filter`, `last_user_content`: покрытие в `tests/domain/test_retrieval.py`, `tests/domain/test_prompt_builder.py` (и дубли в `tests/rag_service/` где применимо).
- [ ] **Доп. unit-тесты** — расширить покрытие вспомогательных функций retrieval/прокси по мере рефакторинга.
- [x] **Интеграция HTTP прокси** — `tests/api/test_http_endpoints.py`: mock/doubles, `POST /v1/chat/completions`, проверки формата и веток RAG (в т.ч. health `/health`).
- [x] **Rerank model** — убрать хардкод `devstral-ios` в `rag_client.rerank()`; читать из env.

---

## Приоритеты для «радикального» скачка качества

1. **RAG:** гибридный поиск (vector + keyword), опционально query expansion; настраиваемые лимиты контекста и порог confidence.
2. **Веб-поиск:** выборочный вызов по запросу, отдельный блок в контексте, без смешивания с RAG-фактами.
3. **Тесты и метрики:** расширять `rag_tests` и JSON/YAML-эталоны при необходимости; метрики латентности/RAG уже пишутся in-memory — добавить экспорт и публичный scrape endpoint при необходимости; health check **сделан**, опционально — probe `/api/embed`.
4. **Конфиг и env:** все URL и имена моделей (чат, embed, rerank) в env/конфиге; версионирование промпта в файле.
5. **Документация:** README, CHANGELOG, описание промпта и принципов самопроверки.

После выполнения п. 1–2 и части п. 3–5 можно считать версию 0.4 с фокусом на «качество без смены модели».

---

## Post MVP

Задачи перенесены в **[POST_MVP.md](POST_MVP.md)**.