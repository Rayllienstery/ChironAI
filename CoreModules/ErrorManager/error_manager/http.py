"""
HTTP error response helpers for WebUI (``/api/webui``) routes.

Produces a consistent JSON body::

    {"error": {"code": "RETRIEVAL_ERROR", "message": "...", "details": [...]}}

The ``/v1`` OpenAI-compat endpoints in ``v1_blueprint.py`` have their own
``_openai_error_response`` format and are **not** touched by this module.

Usage::

    from error_manager.http import error_response
    from error_manager.exceptions import RetrievalError

    # With a ChironError subclass:
    return error_response(RetrievalError("Qdrant down"))

    # With a plain string (status required):
    return error_response("Collection not found", status=404)

    # With an explicit status override:
    return error_response(some_chiron_error, status=503)
"""

from __future__ import annotations

from typing import Any

from flask import jsonify

from error_manager import codes
from error_manager.exceptions import ChironError


def error_response(
    error: ChironError | Exception | str,
    status: int | None = None,
    *,
    extra: dict[str, Any] | None = None,
) -> tuple:
    """
    Build a Flask ``(response, status_code)`` tuple with a structured error body.

    Args:
        error: A ``ChironError`` instance (uses its ``.code`` and ``.http_status``),
               a plain ``str`` (status defaults to 500), or any ``Exception``
               (message taken from ``str(error)``).
        status: Override the HTTP status code. When *None*, ``ChironError.http_status``
                is used for ``ChironError`` instances and 500 for everything else.
        extra:  Additional top-level fields to merge into the response body (e.g.
                ``{"collections": []}`` for partial-success routes).
    """
    if isinstance(error, ChironError):
        body: dict[str, Any] = {"error": error.to_dict()}
        st = status if status is not None else error.http_status
    elif isinstance(error, str):
        body = {"error": {"code": codes.ERROR, "message": error}}
        st = status if status is not None else 500
    else:
        body = {"error": {"code": codes.ERROR, "message": str(error)}}
        st = status if status is not None else 500

    if extra:
        body.update(extra)

    return jsonify(body), st
