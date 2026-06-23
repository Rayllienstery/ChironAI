"""Optional OpenTelemetry wiring for Flask applications."""

from __future__ import annotations

from typing import Any


def configure_flask_otel(app: Any) -> bool:
    """Instrument Flask with OpenTelemetry when the optional package is installed."""

    try:
        from opentelemetry.instrumentation.flask import FlaskInstrumentor
    except Exception:
        app.extensions["otel_instrumented"] = False
        return False
    try:
        FlaskInstrumentor().instrument_app(app)
    except Exception:
        app.extensions["otel_instrumented"] = False
        return False
    app.extensions["otel_instrumented"] = True
    return True


__all__ = ["configure_flask_otel"]
