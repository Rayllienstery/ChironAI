"""POST /v1/external-docs/ingest — delegated to host wiring."""

from __future__ import annotations

from typing import TYPE_CHECKING

from flask import Response, jsonify, request

if TYPE_CHECKING:
    from llm_proxy.contracts import LlmProxyWiring


def run_external_docs_ingest(w: LlmProxyWiring) -> tuple[Response, int]:
    if w.ingest_external_source is None:
        return jsonify({"error": "external_docs ingest not configured"}), 503
    try:
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        return jsonify({"error": "Invalid JSON"}), 400
    source_id = (body.get("source_id") or "").strip()
    if not source_id:
        return jsonify({"error": "source_id is required"}), 400
    payload, status = w.ingest_external_source(source_id)
    return jsonify(payload), status
