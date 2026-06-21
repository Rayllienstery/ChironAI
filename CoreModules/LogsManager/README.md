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

## Proxy Journal Diagnostics

Use LogsManager when a completed RAG Fusion proxy request failed, returned a
surprising answer, or needs trace inspection after the live in-memory trace is
gone.

Fast path:

```python
from logs_manager import get_logs_manager

mgr = get_logs_manager()
row = mgr.get_latest_log()
print(row["id"], row["metadata"].get("trace_id"))
print(row["metadata"].get("response_preview"))
```

Find a specific recent prompt:

```python
row = mgr.find_latest_log_with_user_message("SwiftUI accessibility")
trace = row["metadata"].get("trace") if row else None
```

Fields to inspect first:

- `metadata.trace.request` - resolved model, provider, stream flag, and
  compatibility path.
- `metadata.trace.rag` or `metadata.rag_steps` - embed/search/rerank/context
  sequence and step timings.
- `metadata.rag_context` - retrieved chunks that were sent to the model.
- `metadata.response_preview` - persisted answer preview, useful when the
  client disconnected.

Common interpretations:

- Empty or missing `rag_context` usually points to retrieval/indexing rather
  than LlmProxy wire-format.
- Provider/runtime errors usually require checking the provider extension and
  host runtime registration, not adding direct Ollama calls to core code.
- A missing row means the request did not reach the completed journal path; use
  live traces or backend logs instead.

Guardrails:

- Keep this module read-only.
- Do not expose LogsManager through `/api/webui`; CoreUI already has supported
  log and trace endpoints.
- Do not use it for active streaming state. It reads persisted journal rows
  only.
