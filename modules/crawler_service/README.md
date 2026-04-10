# Crawler Service

## Purpose

- **Rag sources crawl** (default): Playwright BFS + WWDC transcript pipeline writing markdown under `WebUI/rag_sources` (same behavior as legacy `WebUI/app.py crawl`).
- **Port `CrawlRunner`**: `PlaywrightCrawler.crawl()` returns fetched pages without writing to disk (for future md_ingestion HTTP push).

## Install

From repository root (after `chironai-html-md`):

```bash
pip install -e modules/html_md
pip install -e modules/crawler_service
```

Or use `requirements-dev.txt` (includes both).

## CLI

From repo root:

```bash
chironai-crawl crawl [--dry-run] [--source SOURCE_ID] [--all]
```

Environment (optional):

- `CHIRONAI_PROJECT_ROOT` — repository root (default: cwd)
- `CHIRONAI_WEBUI_DIR` — folder containing `rag_sources` and `apple_docs_*.py` (default: `<root>/WebUI`)

## Dependencies

Declared in `pyproject.toml`: `playwright`, `requests`, `html2text`, `lxml`, `PyYAML`, `chironai-html-md`.

## Structure

- `crawler_service/application/crawl_runner.py` — orchestration for `rag_sources` FS crawl
- `crawler_service/domain/` — WWDC parsing, URL rules
- `crawler_service/infrastructure/` — Playwright BFS, `PlaywrightCrawler` (port), Apple fetch thread helper
- `crawler_service/api/cli.py` — `chironai-crawl` entrypoint
- `crawler_service/sources_io.py` — `config/sources.yaml` load/save

HTTP push to md_ingestion remains in `application/use_cases.py` for future wiring.
