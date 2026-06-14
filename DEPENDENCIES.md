# ChironAI Project Dependencies

This document lists all files responsible for dependency management in the project.

## Primary dependency files

### Root level

| File | Description |
|------|-------------|
| `pyproject.toml` | **Primary dependency file**. Contains dependencies for the `chironai` package including runtime and dev dependencies |
| `requirements-dev.txt` | Full dev install: `-e .[dev]` and listed editable packages (see file) |
| `scripts/install_dependencies.bat` | **Windows:** run from `scripts\` - changes to repo root and calls `pip install -r requirements-dev.txt` once (`PIP_ONLY_BINARY=lxml` is set before install) |
| `scripts/build_app.bat` | CoreUI build (`npm run build`); invoked from `build_and_run.bat` |
| `scripts/sync_bundled_extensions.py` | Verify/sync bundled extensions with local repo clones (see `docs/EXTENSIONS_GITHUB_MIGRATION.md`) |
| `scripts/audit_apple_ingest_filter.py` | **Manual offline audit:** chunk/stats for curated Apple Documentation pages; cwd = repo root, requires `WebUI/rag_sources/apple_documentation/` |
| `docker-compose.yml` | Infrastructure dependencies (Qdrant) |

### CoreModules

| File | Description |
|------|-------------|
| `CoreModules/ClawCode/pyproject.toml` | Dependencies for ClawCode agent (flask, requests) |
| `CoreModules/OllamaInteractor/pyproject.toml` | Dependencies for Ollama CLI boundary (requests) |
| `CoreModules/LlmProxy/pyproject.toml` | Dependencies for LLM Proxy (flask) |
| `CoreModules/RagService/pyproject.toml` | Dependencies for RAG Service (flask, requests, httpx, pyyaml) |
| `CoreModules/WebInteraction/pyproject.toml` | Dependencies for Web Interaction (duckduckgo-search, requests, html2text) |
| `CoreModules/MdIngestionService/requirements.txt` | Dependencies for MD Ingestion Service (requests) |

### Modules

| File | Description |
|------|-------------|
| `modules/html_md/pyproject.toml` | Dependencies for HTML→Markdown converter (lxml, html2text) |
| `modules/crawler_service/pyproject.toml` | Dependencies for Crawler Service (requests, playwright, html2text, lxml, PyYAML) |
| `modules/crawler_service/requirements.txt` | Legacy requirements for crawler service |
| `modules/webui_backend/requirements.txt` | Dependencies for WebUI Backend (flask, requests) |

### WebUI

| File | Description |
|------|-------------|
| `CoreModules/CoreUI/package.json` | CoreUI npm commands and dependency ranges |
| `CoreModules/CoreUI/package-lock.json` | CoreUI reproducible npm install lockfile; use `npm ci` for normal installs |

### Vendor

| File | Description |
|------|-------------|
| `vendor/claw-code/versions/.../setup.py` | Setup script for vendor ClawCode |

---

## Key dependencies

### Runtime dependencies (from root pyproject.toml)

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

### Development dependencies

```toml
dev = [
  "pytest>=7.0.0",
  "pytest-cov>=4.0.0",
  "import-linter>=2.0",
  "ruff>=0.8.0",
  "vulture>=2.14",
]
```

### Infrastructure dependencies (Docker)

- **Qdrant** (`qdrant/qdrant:latest`) - vector database

---

## Installing dependencies

### CoreUI frontend

Use the lockfile-first path for regular setup and CI-style checks:

```bash
cd CoreModules/CoreUI
npm ci
npm run build
npm run check:lockfile
```

`npm install` is reserved for intentional dependency updates. Commit `package.json` and `package-lock.json` together when dependency ranges or resolved versions change.

### Full development stack (recommended)

One pass installs the root package with `[dev]` extras and all editable modules from the list:

```bash
pip install -r requirements-dev.txt
```

Root package with dev tools only (without other `-e` entries from the file):

```bash
pip install -e .[dev]
```

For tests, LLM Proxy, RAG Service, crawler, and related `PYTHONPATH` entries use **`requirements-dev.txt`** — it additionally installs `OllamaInteractor`, `LlmProxy`, `RagService`, `html_md`, `crawler_service`.

### Windows

From the `scripts` directory run:

```bat
install_dependencies.bat
```

The script changes to the repository root and calls `pip install -r requirements-dev.txt`. `PIP_ONLY_BINARY=lxml` is set for `lxml` (wheels from PyPI, no source build when available).

**Playwright:** the package is installed via pip; browsers are installed separately when needed:

```bash
python -m playwright install
```

### Starting infrastructure

```bash
docker-compose up -d
```

---

## Dependency structure by module

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
├── ClawCode → flask, requests (not in requirements-dev.txt)
├── OllamaInteractor → requests (requirements-dev.txt)
├── LlmProxy → flask (requirements-dev.txt)
├── RagService → flask, requests, httpx, pyyaml (requirements-dev.txt)
└── WebInteraction → duckduckgo-search, requests, html2text (not in requirements-dev.txt)

Modules/
├── html_md → lxml, html2text
├── crawler_service → requests, playwright, html2text, lxml, PyYAML
└── webui_backend → flask, requests
```

---

## Configuration and compatibility documentation

| Document | Purpose |
|----------|---------|
| `config/README.md` | YAML files and typed getters |
| `config/CONFIG_AUTHORITY.md` | Priority: env / settings / YAML / build |
| `config/ENV_REFERENCE.md` | Environment variable index |
| `infrastructure/ollama/README.md` | Root Ollama adapter boundary and import allowlist |
| `QUALITY_AUDIT.md` | Roadmap cleanup (Passes 1–6) |

---

## Notes

- **Source of truth**: root `pyproject.toml`
- **Python reproducibility**: the current Python stack uses editable installs and dependency ranges, not a fully frozen constraints file. For release-grade reproducibility, add a generated constraints/lock artifact in a dedicated dependency update.
- **CoreUI reproducibility**: `package-lock.json` is the source of truth; normal installs should use `npm ci`.
- **Editable installs**: packages from `requirements-dev.txt` are installed via `-e`; other CoreModules - manually as needed (`pip install -e CoreModules/...`)
- **Docker**: Qdrant is started via docker-compose
- **Python version**: requires Python >=3.10
