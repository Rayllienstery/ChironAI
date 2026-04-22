# TODO_PROXY.md

Цель: поэтапно вернуть “самодеятельность” прокси (RAG и связанные улучшения) **без потери качества базового pass-through**. Любое вмешательство должно быть:

- **Опциональным** (включается явно флагом или только для `ChironAI-Worker`)
- **Изолированным** (1 изменение за раз, легко откатить)
- **Невмешивающимся в user-input** (сообщения пользователя не переписываем; только добавляем отдельные system/контекст-блоки)
- **Воспроизводимым** (trace однозначно показывает, какие режимы были включены)

Текущее состояние (baseline)

- `/v1/chat/completions` всегда делает early-return в primitive passthrough (mediator-only), **RAG pipeline сейчас фактически выключен**.
- Runtime `llm_proxy.tool_helpers` содержит только apply-edit и превью имён tools для trace; старые edit/tool хелперы для интеграционных тестов — в `tests/support/legacy_tool_helpers.py`.
- Ollama `think` на `/v1/chat/completions`: пробрасывается из JSON-тела (`think`) или задаётся дефолтом `LLM_PROXY_DEFAULT_THINK` (`LLM_PROXY_STRICT_THINK` — только тело); ответное «мышление» уходит в `reasoning_content`.
- Ближе к «как Ollama»: в тело `/api/chat` мержится клиентский `options`; в запрос копируются `format` / `keep_alive`; `LLM_PROXY_SKIP_CHAT_CLIENT_DEFAULT_OPTIONS` отключает подмешивание дефолтов `OllamaChatClient`; опционально `LLM_PROXY_AUTOCOMPLETE_PASSTHROUGH_TOOLS` — см. [CoreModules/LlmProxy/README.md](CoreModules/LlmProxy/README.md).

### `/v1` vs прозрачный `/api/chat`

Клиенты вроде Zed говорят по **OpenAI Chat Completions**; Ollama — по **`POST /api/chat`** с другим JSON. Прокси **не может** гонять те же байты end-to-end в обе стороны без нарушения одного из контрактов.

- **Буквальная “байт-прозрачность”** к Ollama: маршрутизация на нативный base URL и прямой проброс `**/api/chat`** (например `forward_ollama_api`), без OpenAI-адаптера.
- **`POST /v1/chat/completions`**: семантический адаптер (логический id → тег Ollama, сообщения OpenAI ↔ Ollama). В `options`: дефолты хоста (если не `LLM_PROXY_SKIP_CHAT_CLIENT_DEFAULT_OPTIONS`), затем поля OpenAI, затем телесный `options` как у Ollama. `thinking` → `reasoning_content`; `format` / `keep_alive` из тела при наличии уходят в `/api/chat`.

---

## Фаза 1 — Вернуть RAG

- [x] **Routing / переключение пайплайна**
  - [x] Убрать unconditional early-return для всех моделей.
  - [x] Включать RAG pipeline

---

## Фаза 2 — Приоритет: user/task > RAG (RAG как опциональный фон)

Цель: RAG-контент не должен “перехватывать управление”.

- [ ] **Prompt contract**
  - [ ] Системный префикс для RAG должен явно говорить:
    - [ ] Primary task = user message/attachments (highest priority)
    - [ ] Retrieved chunks = supplementary knowledge (optional, may be off-topic)
    - [ ] Если конфликт — предпочесть user/attachments
  - [ ] Не переписывать и не “нормализовать” user message; только добавлять отдельный system block.

- [ ] **Acceptance: behaviour**
  - [ ] На вопросах “опиши файл” модель отвечает про файл, даже если retrieval приносит нерелевантные куски.
  - [ ] В trace видно, что retrieval был, но answer следует user.

---

## Фаза 3 — Контроль включения retrieval (флаги и быстрые пути)

Цель: RAG не должен включаться там, где это ухудшает UX.

- [ ] **Флаги клиента**
  - [ ] `skip_rag=true` гарантированно выключает retrieval (даже для `ChironAI-Worker`).
  - [ ] `force_rag=true` принудительно включает retrieval (только для `ChironAI-Worker`, либо явно документировать расширение).

- [ ] **Fast-path для локальных edit flows**
  - [ ] Сохранить/вернуть “local selection edit” fast-path: если IDE делает точечную правку по выделению/диапазону — retrieval пропускаем.

- [ ] **Acceptance: latency**
  - [ ] Для типичных edit-операций время ответа сравнимо с passthrough (retrieval_skipped=true).

---

## Фаза 4 — Коллекции и источники (предсказуемость)

Цель: retrieval идёт из ожидаемой коллекции и всегда понятно почему.

- [ ] **Выбор коллекции**
  - [ ] `body.collection_name` имеет приоритет.
  - [ ] затем `app_settings.rag_collection`
  - [ ] затем `proxy_settings.rag_collection`
  - [ ] затем дефолт.
  - [ ] trace фиксирует `collection_source`.

- [ ] **Acceptance**
  - [ ] В trace однозначно видна `collection_name` и `collection_source`.

---

## Фаза 5 — Web supplement / external docs (строго opt-in)

Цель: вернуть пользу web/external docs без “шумового” вмешательства.

- [ ] **Opt-in**
  - [ ] Включать web supplement только при `fetch_web_knowledge=true` (или явной настройке, но trace должен показывать источник).
  - [ ] Для autocomplete — всегда off.

- [ ] **Acceptance**
  - [ ] Без флага web supplement не используется (trace: used=false).
  - [ ] С флагом — trace показывает trigger/latency/snippets_chars.

---

## Фаза 6 — Tool calling: нативный Ollama

Цель: при наличии OpenAI-совместимого `tools` от клиента прокси использует **нативный** Ollama `/api/chat` (схема tools → ответ с tool_calls), без ветвлений по имени модели.

- [ ] **Policy**
  - [ ] Клиент прислал `tools` и `tool_choice` не `none` → форвард в Ollama native tools + маппинг ответа в OpenAI form.
  - [ ] Опциональный флаг тела запроса `ollama_native_tools: false` только если клиент явно просит отключить (не автоправила по модели).

- [ ] **Acceptance**
  - [ ] В коде нет проверок по тегу/семейству модели для tools или thinking.
  - [ ] Tool flows в Zed работают через тот же нативный путь.

---

## Фаза 7 — Тесты и регрессии (обязательное сопровождение)

- [ ] **Unit tests**
  - [ ] Тесты на routing: `ChironAI-Worker` → RAG, остальные → passthrough.
  - [ ] Тесты на флаги `skip_rag/force_rag`.
  - [ ] Тесты на выбор коллекции и `collection_source`.
  - [ ] Тесты на “no hidden enrichment” в passthrough (не добавляем system_prefix/prompt_name validation).

- [ ] **Golden traces**
  - [ ] Зафиксировать 2-3 эталонных сценария:
    - [ ] passthrough (no rag)
    - [ ] rag on worker
    - [ ] tool flow
  - [ ] Проверять ключевые поля trace (pipeline, steps, collection_source, rag.used).

---

## Нельзя делать (guardrails)

- [ ] Не добавлять “умные” эвристики, которые меняют смысл user запроса.
- [ ] Не включать retrieval/web/tools “тихо” — всегда traceable и opt-in/worker-only.
- [ ] Не возвращать `think`-флаги (сейчас политика: think-agnostic).

