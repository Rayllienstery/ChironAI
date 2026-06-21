"""Tests for structured JSON log formatting."""

from __future__ import annotations

import json
import logging

from infrastructure.logging.structured import StructuredJsonFormatter


def test_structured_json_formatter_includes_correlation_fields() -> None:
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="chironai.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=12,
        msg="hello %s",
        args=("world",),
        exc_info=None,
    )
    record.request_id = "req-1"
    record.trace_id = "trace-1"
    record.component = "tests.core"

    payload = json.loads(formatter.format(record))

    assert payload["message"] == "hello world"
    assert payload["request_id"] == "req-1"
    assert payload["trace_id"] == "trace-1"
    assert payload["module"] == "tests.core"
