# Зависимости проекта ChironAI

Этот документ содержит список всех файлов, отвечающих за управление зависимостями в проекте.

## Основные файлы зависимостей

### Корневой уровень проекта

| Файл | Описание |
|------|----------|
| `pyproject.toml` | **Основной файл зависимостей**. Содержит зависимости для пакета `chironai` включая runtime и dev зависимости |
| `requirements-dev.txt` | Полная dev-установка: `-e .[dev]` и перечисленные editable-пакеты (см. файл) |
| `scripts/install_dependencies.bat` | **Windows:** запуск из `scripts\` — переход в корень репо и один вызов `pip install -r requirements-dev.txt` (перед установкой выставляется `PIP_ONLY_BINARY=lxml`) |
| `docker-compose.yml` | Зависимости инфраструктуры (Qdrant) |

### CoreModules

| Файл | Описание |
|------|----------|
| `CoreModules/ClawCode/pyproject.toml` | Зависимости для ClawCode agent (flask, requests) |
| `CoreModules/OllamaInteractor/pyproject.toml` | Зависимости для Ollama CLI boundary (requests) |
| `CoreModules/LlmProxy/pyproject.toml` | Зависимости для LLM Proxy (flask) |
| `CoreModules/RagService/pyproject.toml` | Зависимости для RAG Service (flask, requests, httpx, pyyaml) |
| `CoreModules/WebInteraction/pyproject.toml` | Зависимости для Web Interaction (duckduckgo-search, requests, html2text) |
| `CoreModules/MdIngestionService/requirements.txt` | Зависимости для MD Ingestion Service (requests) |

### Modules

| Файл | Описание |
|------|----------|
| `modules/html_md/pyproject.toml` | Зависимости для HTML→Markdown конвертера (lxml, html2text) |
| `modules/crawler_service/pyproject.toml` | Зависимости для Crawler Service (requests, playwright, html2text, lxml, PyYAML) |
| `modules/crawler_service/requirements.txt` | Legacy requirements для crawler service |
| `modules/webui_backend/requirements.txt` | Зависимости для WebUI Backend (flask, requests) |

### WebUI

| Файл | Описание |
|------|----------|
| `WebUI/requirements.txt` | Legacy зависимости для WebUI (ссылается на корневой pyproject.toml) |

### Vendor

| Файл | Описание |
|------|----------|
| `vendor/claw-code/versions/.../setup.py` | Setup script для vendor ClawCode |

---

## Ключевые зависимости

### Runtime зависимости (из корневого pyproject.toml)

```toml
dependencies = [
  "flask",
  "requests",
  "duckduckgo-search>=6.0",
  "qdrant-client",
  "langchain-text-splitters",
  "html2text",
  "playwright",
  "lxml>=6.0.0",
]
```

### Development зависимости

```toml
dev = [
  "pytest>=7.0.0",
  "pytest-cov>=4.0.0",
  "import-linter>=2.0",
  "ruff>=0.8.0",
  "vulture>=2.14",
]
```

### Инфраструктурные зависимости (Docker)

- **Qdrant** (`qdrant/qdrant:latest`) - векторная база данных

---

## Установка зависимостей

### Полный стек для разработки (рекомендуется)

Один проход ставит корневой пакет с extras `[dev]` и все editable-модули из списка:

```bash
pip install -r requirements-dev.txt
```

Только корневой пакет с dev-инструментами (без остальных `-e` из файла):

```bash
pip install -e .[dev]
```

Для тестов, LLM Proxy, RAG Service, краулера и смежных путей в `PYTHONPATH` используйте **`requirements-dev.txt`** — он дополнительно ставит `OllamaInteractor`, `LlmProxy`, `RagService`, `html_md`, `crawler_service`.

### Windows

Из каталога `scripts` выполните:

```bat
install_dependencies.bat
```

Скрипт переходит в корень репозитория и вызывает `pip install -r requirements-dev.txt`. Для `lxml` задаётся `PIP_ONLY_BINARY=lxml` (колёса с PyPI, без сборки из исходников, если доступны).

**Playwright:** пакет ставится через pip, браузеры — отдельно при необходимости:

```bash
python -m playwright install
```

### Запуск инфраструктуры

```bash
docker-compose up -d
```

---

## Структура зависимостей по модулям

```
chironai (root)
├── flask
├── requests
├── duckduckgo-search>=6.0
├── qdrant-client
├── langchain-text-splitters
├── html2text
├── playwright
└── lxml>=6.0.0

CoreModules/
├── ClawCode → flask, requests (не в requirements-dev.txt)
├── OllamaInteractor → requests (requirements-dev.txt)
├── LlmProxy → flask (requirements-dev.txt)
├── RagService → flask, requests, httpx, pyyaml (requirements-dev.txt)
└── WebInteraction → duckduckgo-search, requests, html2text (не в requirements-dev.txt)

Modules/
├── html_md → lxml, html2text
├── crawler_service → requests, playwright, html2text, lxml, PyYAML
└── webui_backend → flask, requests
```

---

## Примечания

- **Основной источник истины**: `pyproject.toml` в корне проекта
- **Editable installs**: Пакеты из `requirements-dev.txt` ставятся через `-e`; остальные CoreModules — по необходимости вручную (`pip install -e CoreModules/...`)
- **Docker**: Qdrant запускается через docker-compose
- **Python версия**: Требуется Python >=3.10
