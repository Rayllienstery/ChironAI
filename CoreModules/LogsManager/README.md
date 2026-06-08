# LogsManager

Read-only access to **RAG Fusion proxy journal** rows in `logs/webui.db` (`session_id='proxy'`, `source='proxy'`, `level='INFO'`). Same persisted scope as CoreUI **RAG Fusion Journal** and completed trace history (`metadata.trace`).

**Internal use only** — for Cursor agents and repo scripts. Not exposed via `/api/webui` or CoreUI.

## Install

```bash
pip install -e CoreModules/LogsManager
```

Or via root `requirements-dev.txt`.

## API

```python
from logs_manager import get_logs_manager

mgr = get_logs_manager()

latest = mgr.get_latest_log()
by_id = mgr.get_log_by_id(18561)
matched = mgr.find_latest_log_with_user_message("Найди")
```

| Method | Description |
|--------|-------------|
| `get_latest_log()` | Newest proxy journal row |
| `get_log_by_id(log_id)` | Row by primary key |
| `find_latest_log_with_user_message(substring, scan_limit=500)` | Newest row whose user text contains substring (Unicode case-insensitive) |

## Database path

1. `WEBUI_DB_PATH` environment variable
2. `<project_root>/logs/webui.db`

## Live traces

In-memory live traces (`api/http/proxy_trace.py`) are **not** covered. Use `recent_proxy_traces()` from the monolith for active snapshots. Completed requests are persisted in the journal with full `metadata.trace`.

## Useful metadata fields

- `user_query` — truncated to 500 chars at write time
- `response_preview`
- `trace`, `trace_id`
- `rag_steps`, `rag_context`
