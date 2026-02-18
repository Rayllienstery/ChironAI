# TMRagFetcher

## Mission

TMRagFetcher — это локальный, модель‑агностичный RAG‑слой для разработчиков, который:

- Работает поверх **любой разумной LLM** (локальной или облачной, 7B–70B, в будущем — на RTX 4090).
- Сам обеспечивает **актуальные и точные знания** через модульный фетчер/краулер и RAG:
  - Apple Developer Documentation (iOS, macOS, Swift, SwiftUI, UIKit, Observation и т.д.),
  - расширяемые источники (MDN, блоги, GitHub Docs и др.).
- Даёт **предсказуемый, инженерный результат**:
  - строгая структура ответа (RAG‑факты → реализация → итог),
  - соблюдение архитектуры (Clean/MVVM), Swift 6 strict concurrency, Observation, UI‑правил,
  - контролируемая вариативность (минимум случайности в генерации).
- Имеет **«умный» RAG**:
  - гибридный поиск (vector + keyword), версионность (iOS/Swift), doc_type/section‑aware чанкинг, опциональный rerank LLM,
  - модульный web‑поиск как тонкий слой для дат/релизов, не ломающий дисциплину RAG.
- Поддержан **тестами и метриками**, чтобы качество и стиль ответов были измеримыми и стабильными при смене моделей и источников.

**Коротко:**

> Подключаешь любую LLM → на выходе получаешь поведение, как у очень въедливого, документно‑подкованного senior iOS/Swift‑инженера, а не лотерею.

---

## Текущая версия

- Текущая версия ядра: **0.2**
- Подробный план развития и список сделанного: см. `TODO.md`.

---

## CLI (tmrag)

Единая точка входа из корня проекта:

```bash
python tmrag.py start          # WebUI (Flask)
python tmrag.py crawl          # краулинг
python tmrag.py index          # индексация
python tmrag.py rebuild        # полный пересбор индекса
python tmrag.py update         # crawl + index
python tmrag.py ingest <dir> [--collection NAME]  # индексация локальной папки
python tmrag.py proxy          # RAG-прокси (OpenAI-совместимый)
python tmrag.py test           # pytest
python tmrag.py test-single [url]  # один Apple doc
```

Или: `python -m api.cli <command> ...`

---

## MVP

- [x] **Rename project** — переименовать проект в соответствии с финальным названием. ✅ Переименовано в **TMRagFetcher**.
- [x] **Git** — настроить Git-репозиторий, .gitignore, структуру коммитов. ✅ Локальный Git-репозиторий инициализирован, базовый `.gitignore` добавлен.
- [x] **Configs to the separated file** — вынести все конфигурации (URL Ollama/Qdrant, модели, лимиты RAG, пороги) в отдельный конфиг-файл (YAML/JSON или env). ✅ Реализовано через `config/*.yaml` и модуль `config/__init__.py`.
- [x] **One CLI** — единый CLI для всех операций: `python tmrag.py` или `python -m api.cli` (start, crawl, index, rebuild, update, ingest, proxy, test, test-single).
- [ ] **User friendly log** — улучшить логирование: структурированные логи, user-friendly формат, фильтрация по уровню.
- [x] **Modular architecture** — Layered Architecture реализована: `api/`, `application/`, `domain/`, `infrastructure/`, `config/`, `utils/`, `tests/`. Запуск тестов: `pip install -r requirements-dev.txt` затем `pytest tests/` из корня проекта. Отчёт по покрытию: `pytest tests/ --cov=domain --cov=application --cov-report=term-missing`. Новая модель/источник подключаются через порты в `domain/ports/` и реализации в `infrastructure/` (см. `docs/ARCHITECTURE.md`).
- [ ] **Refactor code** — рефакторинг кода: типизация, единообразие стиля, разделение ответственности.
- [ ] **Move prompt to the Md file** — вынести промпт (`RAG_SYSTEM_PREFIX`) в отдельный Markdown-файл (например `prompts/system_rag_v1.md`) для версионирования и удобного редактирования.
- [ ] **Unify rag client and proxy** — унифицировать логику RAG между `rag_client.py` и `rag_proxy.py`: общая логика поиска, фильтрации, обработки чанков (частично выполнено через domain/application).
- [ ] **Update todo according this changes** — обновить `TODO.md` в соответствии с выполнением задач MVP.

