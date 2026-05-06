# ChironAI — оценка, риски и улучшения (Improvement)

Текст на русском; имена модулей, env vars, endpoints и пути — на английском, как в коде. Для карты модулей см. [Project_Review.md](Project_Review.md). **Порядок работ:** §5 (шкала P0–P3 и срочность) → §6 (бэклог шагов 1–13) → §7 (итерации A–G); текущий следующий шаг указан в конце §7.

---

## 1. Объективная оценка (шкала 1–5)

| Ось | Оценка | Комментарий |
|-----|--------|-------------|
| Архитектура и слои | **4** | Явный hexagonal split (`domain` / `infrastructure` / `application`), контракты в `core/contracts`, отдельные installable CoreModules. Цена: дублирование RAG-логики между корневым `domain` и `rag_service.domain`. |
| Конфигурируемость | **4** | YAML в `config/` + широкие env overrides ([`config/__init__.py`](config/__init__.py), [`config/README.md`](config/README.md)). Отдельные параметры всё ещё размазаны по коду и WebUI settings. |
| Наблюдаемость | **2–3** | Логирование есть; метрики Prometheus в прокси; `GET /health` проверяет Ollama+Qdrant через [`infrastructure/stack_health.py`](infrastructure/stack_health.py) на основном приложении, build proxy и `rag_service`. Полный JSON-лог на всех ветках chat и probe `/api/embed` в health — см. чеклист §6.1. |
| Тесты | **3–4** | Pytest покрывает domain, llm_proxy, rag_service, crawler, md ingestion, web_interaction, часть infrastructure. Нет единого «золотого набора» регрессии ответов LLM в CI как отдельного артефакта (см. TODO). |
| Developer experience | **3** | Много точек входа (`WebUI/rag_proxy.py`, `WebUI/app.py`, `api.cli`, standalone `rag_service.api.http`). Повторяющийся `sys.path.insert` усложняет onboarding. |
| Безопасность секретов | **3** | Ключи по смыслу через env; в [`TODO.md`](TODO.md) явно отмечено усилить `.gitignore` для БД, логов, `.env`. Нужен периодический аудит коммитов. |
| Документация | **3** | README корня и модулей хороши; нет единого CHANGELOG в корне (отмечено в TODO). |

**Итог (субъективно, один абзац):** проект на уровне **зрелого beta**: архитектурная декомпозиция сильная, RAG- и proxy-функциональность богатая, тестовая база шире среднего для подобных репозиториев. Основные пробелы — эксплуатационная прозрачность (health/metrics/structured logs), упрощение запуска без ручного PYTHONPATH, и снижение дублирования между `application.rag.use_cases` и `rag_service.application.use_cases`.

---

## 2. Сильные стороны

1. **Чёткое разделение портов и реализаций** — [`domain/ports/__init__.py`](domain/ports/__init__.py), Qdrant/Ollama в `infrastructure/`, сборка в [`application/container.py`](application/container.py).
2. **OpenAI- и Anthropic-совместимый proxy** — [`CoreModules/LlmProxy`](CoreModules/LlmProxy), wiring в [`api/http/llm_proxy_wiring.py`](api/http/llm_proxy_wiring.py): RAG, tools, streaming, autocomplete model, build presets.
3. **Версионируемые системные промпты** — файлы в `prompts/`, переключение через `rag.prompt` / `RAG_PROMPT` ([`config/rag_prompts.py`](config/rag_prompts.py)).
4. **Продвинутый retrieval** — hybrid / sparse, query expansion, RRF, rerank, фильтры по `doc_type` и intent (см. [`domain/services/retrieval.py`](domain/services/retrieval.py) и [`TODO.md`](TODO.md) по уже закрытым пунктам).
5. **Web supplement без платных API** — [`CoreModules/WebInteraction`](CoreModules/WebInteraction), явные правила «не смешивать с RAG» в тексте fallback-промпта.
6. **Контракты между сервисами** — `core/contracts/*` и README `webui_backend` описывают целевую HTTP-границу.
7. **RAG Tests как формализованный регресс** — markdown-сценарии + CLI `python -m api.cli rag-tests run` ([`rag_tests/README.md`](rag_tests/README.md)).

---

## 3. Критические и высокие риски

### 3.1 Эксплуатация и зависимости от локальных сервисов

- Сбои **Ollama `/api/embed`** (500) приводят к провалу индексации отдельных файлов; в [`TODO.md`](TODO.md) зафиксированы реальные примеры. Нужны retry, бэкпрешер и явная отчётность «сколько пропущено из-за embed» (чеклист шага 3, §6.1).
- **`GET /health`** использует общий [`check_stack_health()`](infrastructure/stack_health.py): HTTP-пробы к Ollama (`/api/tags`) и Qdrant (`/collections`), ответ `status: healthy|unhealthy`, `components`, `503` при сбое. Подключено в [`api/http/rag_routes.py`](api/http/rag_routes.py) (`service: rag_proxy`) и [`rag_service/api/http.py`](CoreModules/RagService/rag_service/api/http.py) (`service: rag_service`). Опционально: отдельная проверка `/api/embed` в health — в чеклисте §6.1.

### 3.2 Дублирование и расхождение поведения

**ADR (канон RAG):** единственная реализация use cases и retrieval — **`application.rag.use_cases`** и **`domain.services.retrieval`**. Пакет **`rag_service`** остаётся HTTP-слоем и wiring’ом; [`rag_service/application/use_cases.py`](CoreModules/RagService/rag_service/application/use_cases.py) **re-export**’ит канон, [`rag_service/domain/services/retrieval.py`](CoreModules/RagService/rag_service/domain/services/retrieval.py) — shim на `domain.services.retrieval`. Запуск `rag_service` по-прежнему требует **корень репозитория на `PYTHONPATH`**.

**Матрица «до консолидации» (для истории):**

| Область | Канон (`application.rag` + `domain`) | Старый дубль `rag_service` |
|--------|----------------------------------------|----------------------------|
| `build_rag_context` | `rag_required_keywords`, `trigger_threshold`, `force_rag`, `infer_query_intent`, merge фильтров, логирование ошибок | Упрощённый skip, `except` → пустой контекст без лога |
| `search_rag` / retrieval | Полный `domain.services.retrieval` (intent, RRF, приоритеты doc_type и т.д.) | Укороченная копия без части эвристик |
| `answer_question` / `prepare_ollama_messages` | Опциональный `rag_context`, разбор `content` list по `type=="text"`, `native_tools`, расширенные параметры | Узкие сигнатуры, иной разбор list content |
| HTTP [`rag_service/api/http.py`](CoreModules/RagService/rag_service/api/http.py) | После консолидации: те же use cases; один проход RAG с передачей `rag_context` в chat/stream | Раньше возможен двойной вызов retrieval (лог + answer) |

Остаётся дублирование **сущностей/промптов** в `rag_service/domain` (например `entities.py`, `prompt_builder`), не критичное для drift retrieval; при желании позже свести к re-export из `domain`.

### 3.3 Хрупкость запуска

- Множественные вставки **`sys.path`** в [`api/http/rag_routes.py`](api/http/rag_routes.py), [`llm_proxy_wiring.py`](api/http/llm_proxy_wiring.py), [`webui_routes.py`](api/http/webui_routes.py), [`WebUI/app.py`](WebUI/app.py). Ошибка cwd или запуск из «не того» каталога ломает импорты.
- **`external_docs_rag`** опционален: `ImportError` глушится в wiring — полезно для dev, но усложняет диагностику «почему нет merged context».

### 3.4 Поддерживаемость WebUI backend

- Файл [`api/http/webui_routes.py`](api/http/webui_routes.py) **очень большой** (тысячи строк). Это повышает риск регрессий, усложняет review и тестирование. Целевая архитектура в [`modules/webui_backend/README.md`](modules/webui_backend/README.md) (слои + HTTP-клиенты к сервисам) пока не заменила монолит полностью.

### 3.5 Внешние нестабильные зависимости

- **DuckDuckGo** и разметка выдачи могут меняться; проект честно документирует это в WebInteraction README. Риск: внезапная деградация web supplement без падения процесса.

## 4. Технический долг

| Тема | Детали |
|------|--------|
| Статическая типизация | В [`TODO.md`](TODO.md): mypy/pyright на ключевых модулях. Сейчас много `type: ignore` и fallback lambda в [`application/container.py`](application/container.py) при `ImportError`. |
| Линтинг | Ruff ограничен `E9` в [`pyproject.toml`](pyproject.toml); «настоящий» pyflakes/F не включены по умолчанию. |
| Язык комментариев | Смесь русского и английского в коде и TODO; для open-source и единообразия с промптами предпочтителен английский в новых изменениях. |
| Документация версий | В TODO: корневой CHANGELOG, расширенный README. |
| `.gitignore` | Явно проверить игнорирование sqlite, логов, `.env`, артефактов crawl (пункт в TODO). |

---

## 5. Шкала приоритета и срочности

Используем **две оси**: влияние на прод/эксплуатацию (P0–P3) и **срок**, когда это разумно брать в работу.

| Уровень | Приоритет | Срочность | Смысл |
|---------|-----------|-----------|--------|
| **P0** | Критический | **Немедленно** | Ложная «здоровость» сервиса, слепые зоны при инцидентах; правим в первую очередь. |
| **P1** | Высокий | **1–2 недели** | Видимость сбоев и отладка (индексация, логи запроса); сильно снижает время расследования. |
| **P2** | Средний | **2–6 недель** | Архитектурный долг и DX; планируется спринтами, без блокировки релизов. |
| **P3** | Низкий | **По мере касания / бэклог** | Качество кода и документации; не блокирует функциональность. |

Связь с рисками: §3.1 → P0–P1; §3.2 → P2; §3.3–3.4 → P2; §3.5 и §4 — в основном P2–P3.

---

## 6. Единый бэклог (по убыванию срочности)

Ниже порядок **для пошагового выполнения**: сначала верх таблицы, затем вниз.

| Шаг | P | Срочность | Задача | Детали / ссылка |
|-----|---|-----------|--------|-----------------|
| **1** | **P0** | Немедленно | **Deep health / readiness** | [`check_stack_health`](infrastructure/stack_health.py) + все HTTP-входы; чеклист **§6.1 шаг 1**. |
| **2** | **P1** | 1–2 недели | **Structured log на chat completion** | Единый `rag_request_completed` (в т.ч. stream), `rag_steps`, web supplement; чеклист **§6.1 шаг 2**. |
| **3** | **P1** | 1–2 недели | **Индексация: skip / fail / embed** | Счётчики, retry embed; чеклист **§6.1 шаг 3** (см. TODO и §3.1). |
| **4** | **P2** | 2–6 недель | **Консолидация RAG use cases** | Выполнено: канон + re-export/shim, §3.2 ADR и матрица. |
| **5** | **P2** | 2–6 недель | **Конфиг лимитов RAG** | `RAG_CONTEXT_*`, `RAG_TOP_K` в env/YAML (TODO §1.2). |
| **6** | **P2** | 2–6 недель | **Запуск без размазанного `sys.path`** | `bootstrap_paths()` или `pip install -e` + единая точка (§3.3). |
| **7** | **P2** | 2–6 недель | **Разрезать `webui_routes.py`** | Blueprints по доменам или shim → `modules/webui_backend` (§3.4). |
| **8** | **P2** | По плану | **Регрессия в CI** | YAML/JSON ожиданий; mock Ollama/Qdrant где возможно (TODO §5.1). |
| **9** | **P3** | Бэклог | **`.gitignore` и секреты** | sqlite, логи, `.env`, артефакты crawl; периодический аудит коммитов (§4, TODO). |
| **10** | **P3** | Бэклог | **Документация версий** | Корневой CHANGELOG, расширенный README (TODO). |
| **11** | **P3** | При касании файлов | **Комментарии на английском** | В новых правках в горячих путях (§4). |
| **12** | **P3** | Постепенно | **Ruff F на CI** | Для новых PR (`--extend-select F`, §4). |
| **13** | **P3** | Долгосрок | **CoreUI только как прокси** | Порты 5001–5003, без дублирующей бизнес-логики в Flask корня (README webui_backend). |

### 6.1 Чеклист критичных шагов (P0–P1)

Отмечайте `[x]` по мере готовности.

**Шаг 1 (P0) — stack health**

- [x] Общий модуль [`infrastructure/stack_health.py`](infrastructure/stack_health.py) (`check_stack_health`, пробы Ollama + Qdrant, корректный `overall` при `HTTP 4xx/5xx`).
- [x] Подключение в [`api/http/rag_routes.py`](api/http/rag_routes.py) (`service: rag_proxy`).
- [x] Подключение в [`rag_service/api/http.py`](CoreModules/RagService/rag_service/api/http.py) (`service: rag_service`; нужен project root на `PYTHONPATH`).
- [x] Тесты: успешный `/health` и `503` при падении зависимости ([`tests/api/test_http_endpoints.py`](tests/api/test_http_endpoints.py)).
- [x] Текст §3.1 и таблица §6 согласованы с кодом.
- [ ] (Опционально) Доп. компонент `ollama_embed` в том же ответе `/health` (минимальный вызов embed API).

**Шаг 2 (P1) — structured log chat completion**

- [x] Общая функция сборки payload для `event: rag_request_completed` в [`CoreModules/LlmProxy/llm_proxy/chat_completions.py`](CoreModules/LlmProxy/llm_proxy/chat_completions.py).
- [x] Поля: `rag_steps` (тайминги RAG как в `rag_timings`), `web_supplement_used`, `stream`, плюс уже существующие `query_hash`, `chunks_count`, `max_score`, `model`, `latency_ms`.
- [x] Один JSON-лог в конце **stream**-ветки (после записи в БД), включая native-tools stream и stream_tool_mode.
- [x] Согласованность **native-tools** и обычного non-stream пути.

**Шаг 3 (P1) — индексация**

- [x] Счётчики в ingest (успех / skip / ошибка чтения / mismatch embed / ошибки embed); сводка [`print_local_ingest_summary`](WebUI/ingest_markdown_common.py) в [`WebUI/ingest_markdown.py`](WebUI/ingest_markdown.py) и [`WebUI/ingest_markdown_local.py`](WebUI/ingest_markdown_local.py).
- [x] Retry с backoff для временных сбоев embed: `RAG_EMBED_MAX_RETRIES`, `RAG_EMBED_RETRY_BASE_SEC` в [`infrastructure/ollama/cli_runner.py`](infrastructure/ollama/cli_runner.py) (`invoke_embed`).
- [x] Те же правила для всех вызовов `invoke_embed` (в т.ч. ingest и runtime embed), когда заданы env или явные `max_retries`.

**Шаг 4 (P2) — консолидация RAG**

- [x] `rag_service.application.use_cases` → re-export [`application.rag.use_cases`](application/rag/use_cases.py).
- [x] `rag_service.domain.services.retrieval` → shim на [`domain.services.retrieval`](domain/services/retrieval.py).
- [x] [`rag_service/api/http.py`](CoreModules/RagService/rag_service/api/http.py): `RagQuestionRequest` / `prompt_builder` из корневого `domain`; `rag_context` в `prepare_ollama_messages` и `answer_question` (один проход RAG).
- [x] ADR и матрица в §3.2.

**Шаг 5 (P2) — лимиты RAG и Builds как SoT**

- [x] Глобальные дефолты: `config/rag.yaml`, `config/retrieval.yaml` и env `RAG_CONTEXT_CHUNK_CHARS`, `RAG_CONTEXT_TOTAL_CHARS` (`get_rag_int`), `RAG_TOP_K` (`get_retrieval_int("top_k", …)`); см. [config/README.md](config/README.md).
- [x] Для **dumb** build id: поля build `context_chunk_chars`, `context_total_chars`, `rag_top_k` в `normalize_build` / WebUI, `merge_build_into_proxy_settings`; LLM Proxy берёт эффективные лимиты из merged `proxy_settings` после выбора build (повторный merge после резолва коллекции из БД, чтобы не затирать overlay).

---

## 7. Пошаговый план работ (итерации)

Делать **строго по номерам шагов** из §6; после каждого шага — короткая проверка (ручной `curl` на health, прогон релевантных тестов, обновление TODO/этого файла при необходимости).

| Итерация | Шаги из §6 | Цель выхода |
|----------|------------|-------------|
| **Итерация A** | 1 | Оркестратор и люди видят реальную готовность Qdrant+Ollama. |
| **Итерация B** | 2 | Можно разобрать инцидент по одному JSON-логу на запрос. |
| **Итерация C** | 3 | Понятно, сколько файлов ушло в skip из-за embed и прочих ошибок. |
| **Итерация D** | 4 | Зафиксирована одна «истина» для RAG pipeline (§3.2 ADR, re-export/shim). |
| **Итерация E** | 5–6 | Меньше «магии» в конфиге и при запуске. |
| **Итерация F** | 7–8 | Проще сопровождать WebUI и ловить регрессии в CI. |
| **Итерация G** | 9–13 | Полировка, безопасность репозитория, долгая консолидация UI. |

**Следующий конкретный шаг:** выполнить **шаг 5** (конфиг лимитов RAG, §6).

---

## 8. Что не трогать без явной необходимости

- **Большой рефакторинг CoreUI** — только при отдельном продуктовом запросе; текущий UI функционален, связан с большим `webui_routes.py`.
- **Массовое включение strict mypy** по всему репозиторию сразу** — лучше инкрементально по пакетам.

---

## 9. Согласование с [`TODO.md`](TODO.md)

Большинство долгосрочных направлений уже перечислены там (concept coverage, A/B промптов, метрики, README/CHANGELOG). Данный файл **дополняет** TODO акцентом на:

- архитектурном дублировании `rag_service` vs корневой RAG;
- размере и поддерживаемости `webui_routes.py`;
- несоответствии «health» реальной готовности стека.

Рекомендуется при закрытии крупных пунктов обновлять и **Improvement.md**, и **Project_Review.md**, чтобы обзор не расходился с кодом.

---

*Оценка носит рекомендательный характер и отражает статический обзор репозитория; приоритеты могут меняться в зависимости от продуктовых целей.*
