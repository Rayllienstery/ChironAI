"""Resolve LLM Proxy pipeline behavior (legacy vs strict pass-through) from settings and env."""

from __future__ import annotations

import os
from typing import Any, TypedDict


class ProxyPipelinePolicy(TypedDict):
    """Effective flags for one chat completion request."""

    tool_policy: str  # "normalize" | "passthrough"
    stateful_guards: bool
    text_tool_retries: bool


def resolve_proxy_pipeline_policy(proxy_settings: dict[str, Any] | None) -> ProxyPipelinePolicy:
    """
    Load policy from ``proxy_settings`` (WebUI / ``proxy_settings`` JSON blob).
    Env overrides (for CI/servers): ``LLM_PROXY_TOOL_POLICY``, ``LLM_PROXY_STATEFUL_GUARDS``,
    ``LLM_PROXY_TEXT_TOOL_RETRIES``.
    """
    ps = proxy_settings if isinstance(proxy_settings, dict) else {}

    t_env = (os.getenv("LLM_PROXY_TOOL_POLICY") or "").strip().lower()
    if t_env in ("normalize", "passthrough"):
        tool_policy = t_env
    else:
        raw = str(ps.get("proxy_tool_policy") or "normalize").strip().lower()
        tool_policy = raw if raw in ("normalize", "passthrough") else "normalize"

    sg_env = (os.getenv("LLM_PROXY_STATEFUL_GUARDS") or "").strip().lower()
    if sg_env in ("0", "false", "no", "off"):
        stateful_guards = False
    elif sg_env in ("1", "true", "yes", "on"):
        stateful_guards = True
    else:
        stateful_guards = bool(ps.get("proxy_stateful_guards", True))

    tr_env = (os.getenv("LLM_PROXY_TEXT_TOOL_RETRIES") or "").strip().lower()
    if tr_env in ("0", "false", "no", "off"):
        text_tool_retries = False
    elif tr_env in ("1", "true", "yes", "on"):
        text_tool_retries = True
    else:
        text_tool_retries = bool(ps.get("proxy_text_tool_retries", True))

    return {
        "tool_policy": tool_policy,
        "stateful_guards": stateful_guards,
        "text_tool_retries": text_tool_retries,
    }


__all__ = ["ProxyPipelinePolicy", "resolve_proxy_pipeline_policy"]
