# ChironAI - Completed Tasks

## Быстрые заметки (из Notes)
- [x] Autocomplete model inside proxy

## Bugs
- [x] Proxy If RAG is not started the response is empty

## 1. RAG (retrieval)

### 1.2 Чанкинг и контекст
- [x] **Семантический чанкинг** — при индексации резать по границам секций/параграфов (заголовок + абзац), а не только по размеру; сохранять `section_path` в payload и при необходимости фильтровать по нему.
- [x] **Лимиты контекста (config/env)** — `RAG_CONTEXT_CHUNK_CHARS`, `RAG_CONTEXT_TOTAL_CHARS`, `RAG_TOP_K` вынесены в `config` / env (`config/__init__.py`, `config/README.md`, `rag.yaml` / `retrieval.yaml`).
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
  - Сделано: `coverage_retry_supplemental_search_enabled` — доп. embed+search по запросу with missing terms, merge в пул, повторный rerank и finalize (`retrieval.yaml`, `use_cases.py`). Отдельный второй вызов chat completion не делался — один проход к модели с улучшенным контекстом.
- [x] **Поднять `top_k` / глубину контекста контролируемо**
  - Сделано: по-прежнему `top_k`, `multi_chunk_*`, `final_context_k`, pass2 и т.д. в YAML; плюс адаптивное расширение `final_k` через coverage gate и опциональный supplemental search.
- [x] **Структурировать контекст для LLM (опционально)**
  - Сделано: `structured_rag_context_enabled` — блоки Concepts / Evidence и нумерация `[n]` в `build_context_block` (`domain/services/prompt_builder.py` + зеркало в RagService); отдельный блок Relations не вводился (при необходимости — следующий шаг).
- [x] **Разделять типы FAIL: retrieval vs reasoning (частично)**
  - Сделано: `rag_metadata.rag_quality` with `failure_class`: `retrieval_gap` при непустых `missing_concepts` в отчёте покрытия, иначе `ok` при наличии целей; structured log `rag_request_completed` — `rag_quality`, `coverage_ratio`. Классификация «ответ модели плох при полном coverage» по-прежнему без автоматики.
- [x] **Усилить prompt-контракт на полноту / пробелы retrieval**
  - Сделано: заметка в system message при `missing_concepts` (`build_system_content`), дополнения в `RAG_SYSTEM_PREFIX` (`config/rag_prompts.py`), файл `prompts/system_rag_v1.md`.
- [x] **Диагностика по каждому запуску (базовый слой)**
  - Сделано: `rag_metadata.rag_trace` + **`coverage_report`** (targets / covered / missing / `coverage_ratio`) + **`rag_quality`** в прокси / webui / rag_service; в trace context assembly — краткий суффикс (coverage, gate_widen, retry_search); CoreUI: таймлайн, зеркало, карта конвейера на RAG / Qdrant.

## 2. Промпт

### 2.1 Содержание
- [x] **Версионирование промпта** — хранить промпты в `prompts/*.md`, подгружать при старте по имени (`rag.prompt` / `RAG_PROMPT`). Реализовано; для воспроизводимости — версионировать изменения в Git; при необходимости вести CHANGELOG в `prompts/`.
- [x] **Два режима промптов: Swift 5 и Swift 6** — реализовать два варианта системного промпта (Swift 5 vs Swift 6), чтобы не путать систему: в одном — правила и принципы под Swift 5, в другом — под Swift 6 (strict concurrency, изоляция, Sendable и т.д.). Переключение режима — через WebUI (выбор в интерфейсе), чтобы пользователь явно указывал целевую версию языка.
- [x] **Явный запрет выдуманных API** — при отсутствии в RAG не генерировать конкретные сигнатуры (например `glassEffect(_:in:)`) без пометки «интерпретация»; при необходимости ужесточить формулировку в блоке «ДАННЫЕ ИЗ RAG».

## 4. Модели и эмбеддинги
- [x] **Чат-модель** — в `rag_proxy.py` модель захардкожена; вынести в env (например `OLLAMA_CHAT_MODEL`) для смены без правки кода.
- [x] **Rerank-модель** — см. п. 1.3; вынести в env.

## 5. Тестирование и оценка качества

### 5.1 Регрессионные тесты
- [x] **Формализованные RAG-сценарии** — каталог `rag_tests/*.md` (вопрос, ожидаемые концепты, опции RAG Strict и т.д.), раннер `python -m api.cli rag-tests run` (см. `rag_tests/README.md`).

## 6. Наблюдаемость и эксплуатация
- [x] **Метрики (in-memory)** — счётчики и гистограммы в LLM Proxy: `rag_requests_total`, `rag_empty_results`, `rag_low_confidence`, latency/tokens и др. (`infrastructure/metrics`, запись из `CoreModules/LlmProxy/llm_proxy/chat_completions.py`).
- [x] **Логирование (structured, proxy)** — JSON-строка `event: rag_request_completed` с `query_hash`, `chunks_count`, `max_score`, `model`, `latency_ms`, `stream`, шагами RAG (`rag_steps`); см. `_rag_request_completed_payload` в `chat_completions.py`.
- [x] **Отдельный error‑логгер WebUI** — `infrastructure/logging/webui_error_logger.py`: файл `webui_errors.log`, ротация, опционально JSON Lines (`LOG_FORMAT=json`); вызовы `log_webui_error` из прокси/WebUI.
- [x] **Health check** — `GET /health` в основном приложении (`api/http/rag_routes.py`), build proxy (`api/http/build_proxy_app.py`), standalone `rag_service` (`CoreModules/RagService/rag_service/api/http.py`); пробы Ollama `/api/tags` и Qdrant `/collections` через `infrastructure/stack_health.py`, при сбое — `503`.
- [x] **Конфиг** — YAML в `config/*.yaml` плюс env overrides (URL Ollama/Qdrant, модели, лимиты RAG, confidence, веб-поиск и т.д.; см. `config/__init__.py`, `config/README.md`).

## 7. Документация и структура проекта
- [x] **Дублирование app.py** — отдельного `app.py` в корне репозитория нет; краул и индексация идут через [`WebUI/app.py`](WebUI/app.py) (см. CLI/README).
- [x] **.gitignore: DB / logs / secrets** — в корневом `.gitignore` уже есть `.env*`, ключи, `*.db`/`*.sqlite*`, `logs/`, `*.log`, кэши, дампы и др.; периодически перепроверять, что новые артефакты не утекают в коммиты.

## 8. Качество кода (проект)
- [x] **Тесты (retrieval / prompt helpers)** — `query_for_retrieval`, `build_qdrant_filter` / `merge_qdrant_filters`, `framework_filter`, `last_user_content`: покрытие в `tests/domain/test_retrieval.py`, `tests/domain/test_prompt_builder.py` (и дубли в `tests/rag_service/` где применимо).
- [x] **Интеграция HTTP прокси** — `tests/api/test_http_endpoints.py`: mock/doubles, `POST /v1/chat/completions`, проверки формата и веток RAG (в т.ч. health `/health`).
- [x] **Rerank model** — убрать хардкод `devstral-ios` в `rag_client.rerank()`; читать из env.
