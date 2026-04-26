# ChironAI

## First of the first
- [ ] Xcode example

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
- [ ] Crawler / Indexer - улучшить понимание того что было проиндексировано, а что нет - Indexed is ok, but skipped count is mandatory
- [ ] Indexing debug - why so much <400 chars filtering, probably it is useful files
- [ ] Indexing debug - Embedding failed: 3
Recent errors (3)
Failed to get embeddings for apple_documentation/visionos-a1eb03fc.md: 500 Server Error: Internal Server Error for url: http://localhost:11434/api/embed
Failed to get embeddings for apple_documentation/menustyle-18306f84.md: 500 Server Error: Internal Server Error for url: http://localhost:11434/api/embed
Failed to get embeddings for wwdc_sessions_2019_plus/wwdc2023-10241-transcript-eng-json-1bc00f62.md: 500 Server Error: Internal Server Error for url: http://localhost:11434/api/embed


## Bugs

## 1. RAG (retrieval)

### 1.2 Чанкинг и контекст
- [ ] **A/B‑тесты лимитов контекста** — сравнение качества для разных моделей и размеров контекста после фиксации базовых лимитов.

### 1.4 Concept Coverage (новый приоритетный слой)

---

## 2. Промпт

### 2.1 Содержание
- [ ] **A/B тесты** — возможность передавать вариант промпта через query param или header (например `X-Prompt-Variant: short`) для сравнения качества без деплоя.

## 4. Модели и эмбеддинги

---

## 5. Тестирование и оценка качества

### 5.1 Регрессионные тесты
- [ ] **Эталонный набор в JSON/YAML** — отдельный файл с парами (запрос, ожидаемые ключевые факты/API или «нет в RAG») и скрипт с парсингом ответа под те же проверки, что в пункте выше (дублирование формата с markdown-тестами по желанию).
- [ ] **Интеграция с app_tester** — `app_tester.py` сейчас тестирует загрузку одной страницы; добавить сценарий: заданный URL → markdown → чанки → эмбеддинг → поиск по тестовому вопросу и проверка, что ожидаемый чанк в топ-N.

### 5.2 Бенчмарки
- [ ] **Латентность** — логировать время: RAG (embed + search + rerank), Ollama chat, полный запрос; выводить перцентили (p50, p95) при запуске тестовой пачки.
- [ ] **Качество retrieval** — для подмножества запросов вручную размеченные релевантные документы; считать Hit@K, MRR или точность «нужный чанк в топ-4».
- [ ] **Качество ответов** — экспертная разметка 20–30 ответов (правильность фактов, соблюдение структуры, отсутствие force unwrap / русских комментариев); зафиксировать baseline для v0.3 и повторять после изменений.

---

## 6. Наблюдаемость и эксплуатация

- [ ] **Экспорт метрик** — выгрузка в Prometheus/StatsD или отдельный `GET /metrics` (сейчас только in-memory collector).
- [ ] **Health: probe `/api/embed`** — опционально добавить проверку эмбеддинга (см. чеклист в `Improvement.md` §6.1).

---

## 7. Документация и структура проекта

- [ ] **README** — в корне проекта: назначение (ChironAI v0.3), требования (Python, Ollama, Qdrant), установка, запуск краулера и индексации, запуск прокси, настройка Zed; ссылки на TODO.md и CHANGELOG.
- [ ] **CHANGELOG** — версии 0.1, 0.2, 0.3 с перечнем изменений (промпт, RAG, принципы самопроверки, Liquid Glass и т.д.).
- [ ] **Описание промпта** — отдельный документ (например `docs/PROMPT.md`): структура ответа, блоки RAG/архитектура/самопроверка, принципы 1–10, когда применяются 2–5 и 10.

---

## 8. Качество кода (проект)

- [ ] **Типизация** — включить проверку типов (mypy или pyright) для `rag_proxy.py`, ключевых функций в `app.py`; исправить замечания.
- [ ] **Русские комментарии** — в кодовой базе часть комментариев на русском; по желанию перевести на английский для единообразия с промптом «код и комментарии на английском».
- [ ] **Доп. unit-тесты** — расширить покрытие вспомогательных функций retrieval/прокси по мере рефакторинга.

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
