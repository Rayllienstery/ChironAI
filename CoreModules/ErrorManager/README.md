# ErrorManager

Canonical error type hierarchy and HTTP response helpers for ChironAI.

## Purpose

- **Single source of truth** for all domain exception classes — eliminates duplicate
  definitions that previously existed in `domain/errors/`, `rag_service/domain/errors.py`,
  `crawler_service/domain/errors.py`, and `MdIngestionService/domain/errors.py`.
- **Consistent HTTP error bodies** for all `/api/webui` routes via `error_response()`.
- **Frontend contract**: every WebUI error response uses the same shape so the frontend
  can parse codes programmatically.

## Package layout

```
error_manager/
  __init__.py      Public re-exports: ChironError, all domain errors, error_response
  exceptions.py    ChironError base + all subclasses
  http.py          error_response() Flask helper (WebUI routes only)
  codes.py         String code constants
```

## HTTP error body contract

```json
{"error": {"code": "RETRIEVAL_ERROR", "message": "Qdrant timed out"}}
{"error": {"code": "VALIDATION_ERROR", "message": "...", "details": ["field x required"]}}
```

The `/v1` OpenAI-compat endpoints keep their own `{"error": {"type": ..., "message": ...}}`
format and are **not** affected by this module.

## Usage

```python
from error_manager import RetrievalError, error_response

# Raise a typed error (infrastructure adapter):
raise RetrievalError("Qdrant vector search timed out", cause=original_exc)

# Return a structured HTTP response (route handler):
return error_response(RetrievalError("No collection selected"), status=400)

# Plain string shorthand:
return error_response("Feature not available", status=501)
```

## Adding a new error type

1. Add a code constant to `codes.py`.
2. Add the subclass to `exceptions.py` with `code` and `http_status`.
3. Re-export from `__init__.py`.
