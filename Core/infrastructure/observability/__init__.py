"""Observability helpers for the Flask host."""

from infrastructure.observability.otel import configure_flask_otel

__all__ = ["configure_flask_otel"]
