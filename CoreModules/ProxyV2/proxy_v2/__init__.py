"""Ollama passthrough proxy with analytics trace."""

from proxy_v2.app import create_pass_proxy_v2_app
from proxy_v2.contracts import ProxyV2Wiring
from proxy_v2.trace_store import get_current_trace, get_current_trace_updated_at, set_current_trace

__all__ = [
    "ProxyV2Wiring",
    "create_pass_proxy_v2_app",
    "get_current_trace",
    "get_current_trace_updated_at",
    "set_current_trace",
]
