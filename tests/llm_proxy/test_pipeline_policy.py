"""Tests for resolve_proxy_pipeline_policy (WebUI + env overrides)."""

from __future__ import annotations

import os

import pytest

from llm_proxy.pipeline_policy import resolve_proxy_pipeline_policy


def test_defaults_when_missing_or_invalid_keys():
    assert resolve_proxy_pipeline_policy({}) == {
        "tool_policy": "normalize",
        "stateful_guards": True,
        "text_tool_retries": True,
    }
    assert resolve_proxy_pipeline_policy({"proxy_tool_policy": "bogus"})["tool_policy"] == "normalize"


def test_settings_override_defaults():
    pol = resolve_proxy_pipeline_policy(
        {
            "proxy_tool_policy": "passthrough",
            "proxy_stateful_guards": False,
            "proxy_text_tool_retries": False,
        }
    )
    assert pol == {
        "tool_policy": "passthrough",
        "stateful_guards": False,
        "text_tool_retries": False,
    }


def test_env_overrides_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROXY_TOOL_POLICY", "passthrough")
    monkeypatch.setenv("LLM_PROXY_STATEFUL_GUARDS", "0")
    monkeypatch.setenv("LLM_PROXY_TEXT_TOOL_RETRIES", "off")
    pol = resolve_proxy_pipeline_policy(
        {"proxy_tool_policy": "normalize", "proxy_stateful_guards": True, "proxy_text_tool_retries": True}
    )
    assert pol["tool_policy"] == "passthrough"
    assert pol["stateful_guards"] is False
    assert pol["text_tool_retries"] is False


def test_env_normalize_explicit(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_PROXY_TOOL_POLICY", "normalize")
    monkeypatch.setenv("LLM_PROXY_STATEFUL_GUARDS", "1")
    monkeypatch.setenv("LLM_PROXY_TEXT_TOOL_RETRIES", "true")
    pol = resolve_proxy_pipeline_policy({"proxy_tool_policy": "passthrough"})
    assert pol["tool_policy"] == "normalize"
    assert pol["stateful_guards"] is True
    assert pol["text_tool_retries"] is True
