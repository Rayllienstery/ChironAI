# ChironAI v0.4

## First of the first
- [ ] Xcode example

## Быстрые заметки (из Notes)

- [ ] Auto start docker
- [ ] Esp 32 integration
- [ ] Live session fix ui
- [ ] Unificate right bottom menu
- [ ] iPhone notifications
- [ ] Web framework search - work the same as crawl...

- [ ] Check RAG Quality TASK
- [ ] Crawler / Indexer - улучшить понимание того что было проиндексировано, а что нет - Indexed is ok, but skipped count is mandatory
- [ ] Indexing debug - why so much <400 chars filtering, probably it is useful files
- [ ] Indexing debug - Embedding failed: 3

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
- [x] **Эталонный набор в JSON/YAML** — реализовано через Markdown-тесты в `rag_tests/` и хранение результатов в SQLite.
- [x] **Интеграция с app_tester** — реализовано через `rag_tests_routes.py` и `runner.py`.

### 5.2 Бенчмарки
- [x] **Латентность** — логируется `latency_ms`, отображается в UI (p50/p95).
- [x] **Качество retrieval** — реализовано в RAG тестах (Hit@K, MRR).
- [x] **Качество ответов** — реализована валидация концептов в `validator.py`.

---

## 6. Наблюдаемость и эксплуатация

- [ ] **Экспорт метрик** — выгрузка в Prometheus/StatsD или отдельный `GET /metrics` (сейчас только in-memory collector).
- [ ] **Health: probe `/api/embed`** — добавить проверку эмбеддинга (см. чеклист в `Improvement.md` §6.1).

---

## 7. Документация и структура проекта

- [x] **README** — в корне проекта: назначение (ChironAI v0.3), требования, установка, запуск.
- [ ] **CHANGELOG** — версии 0.1, 0.2, 0.3, 0.4 с перечнем изменений.
- [ ] **Описание промпта** — отдельный документ (например `docs/PROMPT.md`).

---

## 8. Качество кода (проект)

- [ ] **Типизация** — включить проверку типов (mypy или pyright) для `rag_proxy.py`, ключевых функций в `app.py`.
- [x] **Русские комментарии** — перевести на английский для единообразия.

---

## Приоритеты v0.4 (Качество и Эксплуатация)

1. **Наблюдаемость:** [ ] Экспорт метрик в Prometheus (`/metrics`), [ ] Health probe для `/api/embed`.
2. **RAG:** [ ] Улучшение отчётности индексатора (skipped count), [ ] Отладка фильтрации коротких файлов (<400 симв).
3. **Промпт:** [ ] Механизм A/B тестов промптов через заголовки.
4. **Документация:** [ ] Создание CHANGELOG.md, [ ] Описание архитектуры промпта.

---

## Post MVP
Задачи перенесены в **[POST_MVP.md](POST_MVP.md)**.
