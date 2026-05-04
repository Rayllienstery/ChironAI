# ChironAI: строгий обзор проекта

Дата: 2026-05-04  
Проверка: статический аудит репозитория + `pytest` + сверка с внешними best practices  
Результат тестов: `492 passed in 4.64s` + `npm.cmd run build` для CoreUI

## Executive Summary

**Тезис: ChironAI уже выглядит как зрелая beta-платформа, а не как прототип.**  
Пояснение: в проекте есть модульная RAG-архитектура, OpenAI/Anthropic-compatible proxy, Qdrant, Ollama, WebUI, crawler, ingestion, regression tests для RAG и отдельные CoreModules. Наличие 492 проходящих тестов и зеленой frontend-сборки - сильный сигнал дисциплины.

**Тезис: главный риск проекта - не отсутствие возможностей, а избыточная сложность и незавершенная миграция.**  
Пояснение: рядом живут legacy-слои `api/application/domain/infrastructure`, новые `CoreModules/*`, новые `modules/*`, thin wrappers и старые монолитные маршруты. Это нормально для активной миграции, но опасно для долгой поддержки.

**Тезис: RAG-подход выбран верно: dense + sparse + rerank + trace.**  
Пояснение: Qdrant прямо рекомендует hybrid retrieval и reranking как способ совместить recall и precision, а проект уже имеет `hybrid_sparse_enabled`, RRF merge, rerank pool, coverage gate и pipeline trace.

**Тезис: эксплуатационная готовность ниже архитектурной зрелости.**  
Пояснение: health есть, structured logs есть, `/v1*` теперь закрыт WebUI-managed API key, но до полноценного production-контура еще есть путь: metrics export не завершен, WebUI/backend не полностью отделен, часть внешних интеграций fragile по природе.

Итоговая оценка проекта: **80/100**.

## Обновление: WebUI-First Security

**Тезис: решение управлять proxy key через WebUI соответствует продуктовой философии проекта.**  
Пояснение: ChironAI развивается как локальная платформа, а не набор CLI-скриптов. Поэтому генерация, раскрытие, ротация и удаление ключа должны жить в WebUI. Env/YAML остаются bootstrap/recovery слоями, но не основным интерфейсом для повседневной работы.

**Тезис: защита реально выросла, но модель осознанно удобнее, чем GitHub-style show-once.**  
Пояснение: `/v1*` больше не открыт случайно при bind на сеть: нужен Chiron API key. При этом ключ recoverable, потому что один и тот же secret используется в нескольких IDE, OpenWebUI provider settings и внешних OpenAI-compatible клиентах. Это компромисс: слабее, чем невосстановимый токен, но лучше подходит локальной WebUI-first системе.

**Тезис: текущий trust boundary надо явно держать в голове.**  
Пояснение: защищены Chiron OpenAI/Anthropic-compatible `/v1*` endpoints. Ollama passthrough `/api/tags`, `/api/show`, `/api/generate`, `/api/chat` намеренно оставлены без Chiron key, чтобы не ломать OpenWebUI/Ollama-style backend. Это не баг, а compatibility-решение, но его нужно показывать в UI и документации.

## Что Есть В Проекте

| Область | Оценка | Что есть | Пояснение |
|---|---:|---|---|
| Архитектура | 82 | Hexagonal/layered split, CoreModules, contracts | Слои читаются, domain ports есть, но миграция не завершена. |
| RAG pipeline | 86 | query prep, dense/sparse search, rerank, coverage, context assembly | По функциям это выше среднего для локальной RAG-системы. |
| LLM Proxy | 83 | `/v1/chat/completions`, `/v1/messages`, `/v1/completions`, tools, vision, builds | Поверхность богатая, но файл handler слишком большой. |
| Ingestion | 78 | filtering, normalization, chunking, md_indexer, retries | Хорошая основа; нужна более строгая отчетность качества индекса. |
| WebUI | 76 | React/Vite SPA, dashboard, logs, RAG settings, tests UI, proxy key management | Функционально богато и лучше закрывает админские сценарии, но компоненты местами перегружены. |
| Tests | 89 | 492 green tests + CoreUI build | Отличный показатель; не хватает CI-качества LLM/RAG ответов как стабильного baseline. |
| Observability | 72 | proxy traces, request logs, timing fields, health endpoints | Уже полезно, но до production observability еще шаг. |
| Security | 73 | WebUI-managed key для `/v1*`, path safety в apply-edit, SSRF flags off by default | Существенно лучше: прямой доступ к Chiron `/v1*` теперь fail-closed. Риск остается в recoverable secret и открытом `/api/*` compatibility path. |
| DX / запуск | 68 | docs, scripts, editable modules | Много entrypoints и `PYTHONPATH`-логики усложняют onboarding. |
| Документация | 76 | README, architecture docs, module docs, TODO/Improvement | Документов много, но часть текстов повреждена кодировкой. |

## Архитектура

**Тезис: целевая архитектура хорошая: Presentation -> Application -> Domain -> Infrastructure.**  
Пояснение: `docs/ARCHITECTURE.md`, `docs/MODULAR_STRUCTURE.md`, `domain/ports/*`, `CoreModules/RagService`, `CoreModules/MdIngestionService`, `CoreModules/LlmProxy` показывают правильное направление.

**Тезис: проект сейчас в гибридном состоянии между монолитом и модульной платформой.**  
Пояснение: `api/http/webui_routes.py` содержит 4247 строк, `CoreModules/LlmProxy/llm_proxy/chat_completions.py` - 4118 строк. Это не авария, но это явные центры риска.

**Тезис: границы модулей уже осмыслены, но не всегда доведены до физической изоляции.**  
Пояснение: `modules/webui_backend` существует как target backend, но основной WebUI API все еще живет в legacy Flask routes.

**Тезис: import-linter контракт для domain - правильное решение.**  
Пояснение: `pyproject.toml` запрещает `domain -> application/api/infrastructure`, что защищает внутренний слой от расползания зависимостей.

## RAG Pipeline

**Тезис: RAG pipeline - самая сильная часть проекта.**  
Пояснение: pipeline разбит на `query_prep`, `embed_search_pass1`, `concept_expansion_pass2`, `metadata_rank`, `rerank`, `coverage_gate`, `coverage_supplemental`, `context_assembly`.

**Тезис: hybrid search включен по умолчанию, и это правильно.**  
Пояснение: dense embeddings хорошо ловят смысл, sparse signal ловит точные API/symbol terms. Для Swift/iOS-документации это критично, потому что `NavigationStack`, `@Observable`, `UIViewController` нельзя надежно искать только семантически.

**Тезис: coverage gate - сильная идея, но сейчас часть advanced-флагов выключена.**  
Пояснение: `coverage_aware_selection`, `coverage_gate_enabled`, `coverage_retry_supplemental_search_enabled`, `query_expansion_enabled`, `concept_expansion_enabled` в `config/retrieval.yaml` по умолчанию false. Это снижает риск latency, но оставляет качество не максимальным.

**Тезис: rerank реализован практично, но модель по умолчанию консервативная.**  
Пояснение: fallback `bbjson/bge-reranker-base` легкий и быстрый, но для сложных code/docs запросов лучше иметь профиль на `bge-reranker-v2-m3`.

**Тезис: RAG tests - большой плюс.**  
Пояснение: `rag_tests/*` описывает вопросы, expected concepts, strict RAG overlap. Это правильная форма регрессии для RAG, потому что unit tests не ловят деградацию retrieval quality.

## LLM Proxy

**Тезис: LLM Proxy функционально мощный.**  
Пояснение: поддерживаются OpenAI chat, legacy completions, Anthropic Messages, Ollama passthrough, build presets, tool calls, vision data URLs, external docs ingest, apply-edit.

**Тезис: OpenAI-compatible слой перегружен ответственностями.**  
Пояснение: `chat_completions.py` делает routing, RAG, web supplement, tool mediation, streaming, Gemini compatibility, logs, token estimates, budget compaction и response shaping. Это много для одного файла.

**Тезис: single-chunk SSE workaround честно задокументирован и нужен.**  
Пояснение: `known_bugs.md` правильно разделяет transport problem и model/tool behavior problem. Это зрелый подход: не скрывать ограничение, а явно дать переключатель.

**Тезис: `/v1*` proxy auth теперь закрывает главный сетевой риск, но это не полноценная zero-trust модель.**  
Пояснение: Chiron `/v1`, `/v1/models`, `/v1/chat/completions`, `/v1/messages`, `/v1/responses`, `/v1/completions`, `/v1/files/apply-edit` и `/v1/external-docs/ingest` теперь fail-closed: без ключа возвращается `503`, с неверным или отсутствующим credential - `401`. Ключ генерируется и раскрывается через WebUI, хранится в `app_settings` как recoverable admin secret плюс `sha256`, а runtime-проверка идет через hash и constant-time compare. `/api/tags`, `/api/show`, `/api/generate`, `/api/chat` оставлены без Chiron key ради OpenWebUI/Ollama compatibility.

## CoreUI

**Тезис: WebUI богатый, но компоненты уже на грани поддерживаемости.**  
Пояснение: `RagTab.jsx` - 1520 строк, `LlmProxyBuildsTab.jsx` - 1565 строк. Это сигнал разделить state/data fetching/forms/panels.

**Тезис: дизайн-система начала формироваться.**  
Пояснение: есть `CoreUIButton`, `CoreUIPillTabs`, `CoreUISlider`, tokens/styles, dashboard cards. Это лучше, чем разрозненный CSS.

**Тезис: frontend lacks formal test runner.**  
Пояснение: `package.json` имеет `build`, `dev`, `preview`, `knip`, но нет `test`, `lint`, `typecheck`. Для UI с таким количеством состояний это слабое место.

## Ingestion / Crawler / Index Quality

**Тезис: ingestion pipeline аккуратный, но нуждается в более строгой диагностике качества.**  
Пояснение: есть filename/content filters, `md_indexer`, noise headings, chunk sizes, retry settings. Но TODO прямо фиксирует боль: нужно ясно видеть indexed/skipped/failed counts и причины.

**Тезис: chunking параметры разумные.**  
Пояснение: `chunk_max_size: 1200`, overlap 150, min alpha/words фильтры подходят для markdown docs. Риск: слишком агрессивный low-signal filter может выбросить короткие, но важные API pages.

**Тезис: embedding failures обработаны лучше, чем раньше, но должны стать first-class метрикой.**  
Пояснение: есть retry/backoff tests, но UI/отчеты должны прямо показывать `embed_failed`, `skipped_by_filter`, `skipped_low_signal`, `upsert_failed`.

## Что Не Хватает

| Приоритет | Пробел | Почему важно | Что сделать |
|---|---|---|---|
| Done | Auth / network safety для Chiron `/v1*` | Локальный LLM proxy без ключа опасен при bind на сеть | Реализован WebUI-managed API key: generate/reveal/regenerate/delete, fail-closed `/v1*`, dashboard hint. Осталось отдельно решить policy для raw `/api/*`. |
| P1 | Разрезать `webui_routes.py` | 4247 строк повышают риск регрессий | Blueprints: logs, settings, models, rag, crawler, service-control. |
| P1 | Разрезать `chat_completions.py` | 4118 строк - слишком много логики в одном handler | Выделить request normalization, RAG enrichment, tool mediation, streaming, tracing. |
| P1 | Frontend tests | UI сложный, а тестового контура нет | Добавить Vitest + React Testing Library минимум для utils и critical components. |
| P1 | RAG quality baseline в CI | Unit tests зеленые, но retrieval quality может падать | Запуск `rag-tests` на mock/snapshot corpus + метрики Hit@K/MRR/strict overlap. |
| P1 | Metrics export | In-memory metrics мало для эксплуатации | `/metrics` Prometheus или structured JSON endpoint. |
| P2 | Typed config authority | YAML/env/UI settings пересекаются | Один typed config facade с source labels и validation. |
| P2 | Packaging / запуск без `sys.path` | Сейчас много entrypoints и path magic | Укрепить editable install или общий bootstrap только в одном месте. |
| P2 | CHANGELOG / release discipline | Нельзя быстро понять изменения между версиями | Ввести root `CHANGELOG.md` и migration notes. |
| P2 | Кодировка документов | Часть русских docs отображается mojibake | Перекодировать affected markdown в UTF-8. |
| P3 | Strict lint/typecheck | Ruff сейчас почти только syntax-level | Постепенно включать `ruff --extend-select F`, затем pyright/mypy для hot paths. |

## Оценка Моделей 0-100

Шкала: качество для ChironAI = RAG usefulness + code/docs reasoning + tool compatibility + latency + local/privacy + стабильность. Это не глобальный leaderboard, а прикладная оценка для данного проекта.

| Модель / класс | Роль | Score | Quality | Latency | Tools | Context | Privacy | Cost | Pros | Cons |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| `mxbai-embed-large` | embeddings | 92 | 93 | 78 | n/a | 55 | 100 | 96 | Сильная embedding-модель для локального RAG; в Ollama официально описана как SOTA-class для своего размера. | 512 context в Ollama card ограничивает длинные query/chunk prefixes; требует дисциплины chunking. |
| `bbjson/bge-reranker-base` | rerank | 76 | 74 | 88 | n/a | 52 | 100 | 96 | Хороший быстрый fallback, низкий operational cost. | Для сложной code retrieval может уступать v2/multilingual rerankers. |
| `bge-reranker-v2-m3` | rerank | 86 | 88 | 70 | n/a | 78 | 100 | 94 | Лучший кандидат для quality profile: 8K контекст у Ollama-вариантов, сильнее для длинных docs. | Медленнее base; нужно явно протестировать на локальном железе. |
| Qdrant dense+sparse hybrid | retrieval strategy | 90 | 91 | 80 | n/a | n/a | 100 | 95 | Совпадает с best practice: semantic + keyword retrieval перед rerank. | Текущий sparse hash/BM25-like слой слабее полноценного BM25/SPLADE. |
| `ChironAI-Autocomplete` | logical fast model | 72 | 60 | 95 | 50 | 55 | 100 | 96 | Полезно как отдельный быстрый режим без RAG. | Не конкретная модель; качество зависит от настроенного Ollama tag. |
| Concrete Ollama chat tag | local chat | 78 | 74 | 82 | 65 | 65 | 100 | 96 | Гибко: пользователь выбирает модель, приватность и низкая стоимость. | Нет гарантии tools/vision/context; поведение зависит от tag. |
| Llama 3.x / 3.2 class | local chat/code | 80 | 78 | 82 | 70 | 65 | 100 | 96 | Хороший default для локального общего ассистента. | Для глубокого Swift/iOS reasoning может ошибаться без сильного RAG. |
| Qwen2.5/3 coder class | code reasoning | 84 | 86 | 72 | 72 | 75 | 100 | 94 | Обычно сильнее для code edits и structured reasoning. | Может быть тяжелее, требует подбора quantization. |
| DeepSeek coder class | code reasoning | 83 | 87 | 68 | 70 | 72 | 100 | 94 | Сильный кодовый профиль. | Tool calling и форматирование могут требовать extra guardrails. |
| Mistral/Mixtral class | general local chat | 76 | 75 | 76 | 64 | 70 | 100 | 94 | Хороший баланс качества и скорости. | Не лучший выбор именно для Apple docs RAG без настройки. |
| Phi small class | fast local | 68 | 60 | 94 | 50 | 55 | 100 | 97 | Быстро, удобно для autocomplete/черновиков. | Слабее в сложных multi-step задачах. |
| Gemini family via compatibility logic | external/tools | 88 | 90 | 70 | 90 | 92 | 55 | 55 | Проект уже учитывает Gemini thought/tool quirks; хорошо для agent clients. | External dependency, cost/privacy, strict protocol quirks. |
| OpenAI-compatible external frontier | external reasoning | 91 | 94 | 72 | 92 | 90 | 45 | 45 | Лучшее качество и tool reliability для сложных задач. | Не локально, платно, требует auth/security story. |
| Raw `/api/chat` passthrough | compatibility mode | 66 | 70 | 84 | 65 | 65 | 100 | 96 | Удобно для клиентов, которым нужен Ollama base URL. | Обходит RAG/templates/proxy logs; хуже наблюдаемость. |
| Legacy `/v1/completions` | edit prediction/legacy | 62 | 62 | 82 | 20 | 55 | 100 | 96 | Нужен для старых клиентов и Zed edit prediction. | Нет RAG, web supplement и нормальной chat semantics. |

## Рекомендованные Профили Моделей

**Тезис: один default profile не закроет все сценарии.**  
Пояснение: autocomplete, RAG answering, code editing и rerank имеют разные требования по latency/context/tool reliability.

| Профиль | Embed | Rerank | Chat | Когда использовать |
|---|---|---|---|
| Balanced local | `mxbai-embed-large` | `bbjson/bge-reranker-base` | Llama/Qwen medium tag | Ежедневная работа, слабое железо. |
| Quality RAG | `mxbai-embed-large` | `bge-reranker-v2-m3` | Qwen coder / strong local | Сложные Swift/iOS ответы, важна точность retrieval. |
| Fast autocomplete | none/RAG off | none | small Phi/Qwen/Llama tag | Inline completions и быстрые подсказки. |
| Agent tools | `mxbai-embed-large` | v2-m3 или off | tool-capable model | IDE agents, file edits, multi-turn tools. |
| External premium | configurable | optional | OpenAI/Gemini class | Когда качество важнее приватности и стоимости. |

## Best Practices Сверка

**Тезис: hybrid retrieval + rerank в проекте соответствует современным рекомендациям.**  
Пояснение: Qdrant описывает dense + sparse retrieval с последующим rerank как способ сначала расширить recall, а потом уточнить relevance на меньшем наборе кандидатов.

**Тезис: проекту стоит двигаться от эвристического sparse к более стандартному sparse model профилю.**  
Пояснение: текущий sparse layer полезен, но полноценные BM25/SPLADE/miniCOIL профили лучше объяснимы и проще сравниваются метриками.

**Тезис: rerank надо держать включаемым профилем, а не безусловным default.**  
Пояснение: rerank улучшает precision, но добавляет latency. Лучший UX - build/profile переключатель: fast, balanced, quality.

**Тезис: auth story для OpenAI-compatible proxy появился, и это заметный шаг вперед.**  
Пояснение: OpenAI-compatible endpoint легко подключить к внешним клиентам, поэтому WebUI-managed key для `/v1*` резко снижает риск случайной экспозиции. Компромисс осознанный: ключ recoverable, потому что один секрет нужен нескольким IDE/OpenWebUI provider settings; это слабее, чем show-once токены GitHub, но лучше соответствует WebUI-first локальной системе.

## Самые Сильные Стороны

1. **RAG pipeline не примитивный.**  
   Пояснение: есть multi-stage retrieval, metadata ranking, rerank, coverage logic и context assembly.

2. **Тестовая база реально широкая.**  
   Пояснение: 492 теста покрывают API, RAG, LLM proxy, tools, ingestion, crawler, WebInteraction, ServiceStarter; CoreUI production build также проходит.

3. **Proxy умеет реальные IDE/agent сценарии.**  
   Пояснение: tool calls, apply-edit, streaming quirks, Gemini compatibility и Responses-like tests показывают практический опыт.

4. **Конфигурация вынесена в YAML/env/UI.**  
   Пояснение: это хорошо для экспериментов, особенно RAG и модельных профилей.

5. **Документы фиксируют ограничения, а не маскируют их.**  
   Пояснение: `known_bugs.md`, `Improvement.md`, TODO и module READMEs помогают понять историю решений.

## Самые Слабые Места

1. **God-files.**  
   Пояснение: 4247 строк routes и 4118 строк chat handler - это main risk для review, regression и onboarding.

2. **Незавершенная модульная миграция.**  
   Пояснение: target architecture описана, но legacy backend все еще несет много реальной логики.

3. **Security default стал заметно лучше, но `/api/*` остается compatibility-исключением.**  
   Пояснение: `/v1*` теперь требует Chiron key и fail-closed, но raw Ollama passthrough routes оставлены открытыми, чтобы не ломать OpenWebUI/Ollama-style backend. Это надо явно считать trust-boundary решением.

4. **Frontend без тестового контура.**  
   Пояснение: при таком объеме UI-логики нужен хотя бы Vitest для reducers/utils/state mapping.

5. **RAG quality пока не закреплен как release gate.**  
   Пояснение: `rag_tests` есть, но нужен стабильный baseline и численные retrieval metrics в CI.

## Практический Roadmap

### 1. Сразу

**Закрепить новую WebUI-first security model.**  
Пояснение: auth guard для `/v1*` уже реализован через WebUI-managed key. Следующий шаг - в UI явно показывать trust boundary: `/v1*` protected, `/api/*` compatibility passthrough, key recoverable admin secret, regenerate invalidates old clients.

**Ввести quality build profile: `fast`, `balanced`, `quality`.**  
Пояснение: пользователь сможет включать `bge-reranker-v2-m3`, coverage gate и larger context только там, где это нужно.

**Разрезать `chat_completions.py` по внутренним сервисам.**  
Пояснение: начать можно без изменения поведения: вынести trace helpers, streaming helpers, model/build resolution, tool mediation.

### 2. В ближайший цикл

**Разделить `webui_routes.py` на blueprints.**  
Пояснение: logs/settings/rag/crawler/models/service-control должны иметь отдельные файлы и тестовые зоны.

**Добавить frontend `test` script.**  
Пояснение: Vitest + React Testing Library для `proxyTraceModel`, `modelTesterMarkdown`, build normalization UI, RAG settings mapping.

**Сделать RAG regression dashboard обязательным.**  
Пояснение: сохранять pass rate, strict overlap, retrieval_used, Hit@K/MRR по тестовому corpus.

### 3. После стабилизации

**Усилить config authority.**  
Пояснение: сейчас YAML/env/UI/build overlays работают, но требуют постоянной осторожности. Нужны typed effective settings с source labels.

**Постепенно включать lint/typecheck.**  
Пояснение: начать с новых/изменяемых файлов и hot paths, не пытаться типизировать весь monorepo за один заход.

**Перекодировать поврежденные русскоязычные markdown docs.**  
Пояснение: mojibake в TODO/Improvement снижает полезность документации и портит поиск по репозиторию.

## Источники И Сверка

- Qdrant: Hybrid Search with Reranking - https://qdrant.tech/documentation/advanced-tutorials/reranking-hybrid-search/
- Qdrant docs sections: Hybrid Queries, Search Relevance, Retrieval Quality Evaluation - https://qdrant.tech/documentation/
- Ollama model card: `mxbai-embed-large` - https://registry.ollama.ai/library/mxbai-embed-large
- Ollama community cards for `bge-reranker-v2-m3` variants - https://ollama.com/search?q=bge-reranker-v2-m3
- Local evidence: `pyproject.toml`, `config/*.yaml`, `CoreModules/*/README.md`, `CoreModules/LlmProxy/llm_proxy/api_key.py`, `CoreModules/CoreUI/src/components/LlmProxyTab.jsx`, `api/http/webui_routes.py`, `docs/ARCHITECTURE.md`, `docs/MODULAR_STRUCTURE.md`, `known_bugs.md`, `rag_tests/README.md`

## Финальная Оценка

**ChironAI: 80/100 сейчас, 86/100 достижимо без переписывания ядра.**  
Пояснение: ядро RAG и proxy уже сильные, а security default для `/v1*` стал существенно лучше. Самый большой дальнейший прирост даст не новая модель, а инженерная уборка: явная trust-boundary политика для `/api/*`, разрезание God-files, frontend tests, RAG quality gates и единый config/effective-profile слой.

