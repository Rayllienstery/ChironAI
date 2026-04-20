"""Canonical LLM proxy pipeline step contract + registry."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from llm_proxy.pipeline_steps.merged_docs_step import MergedDocsStepMeta
from llm_proxy.pipeline_steps.web_supplement_step import WebSupplementStepMeta


@dataclass(frozen=True)
class ProxyStepDefinition:
    id: str
    icon: str
    title: str
    description: str


_PROXY_PIPELINE_STEPS: tuple[ProxyStepDefinition, ...] = (
    ProxyStepDefinition(
        id="parse",
        icon="input",
        title="Parse / gate",
        description="Prepare request, resolve settings, and decide retrieval/supplement gates.",
    ),
    ProxyStepDefinition(
        id="rag",
        icon="database",
        title="Vector RAG",
        description="Run RAG retrieval against the selected Qdrant collection when configured.",
    ),
    ProxyStepDefinition(
        id="hybrid",
        icon="merge_type",
        title="Hybrid sparse",
        description="Use dense+sparse retrieval fusion when hybrid sparse is enabled.",
    ),
    ProxyStepDefinition(
        id="rerank",
        icon="swap_vert",
        title="LLM rerank",
        description="Rerank retrieved chunks when rerank-for-rag is enabled.",
    ),
    ProxyStepDefinition(
        id="context",
        icon="construction",
        title="Build context",
        description="Assemble final context block for prompt construction.",
    ),
    ProxyStepDefinition(
        id="skills",
        icon="extension",
        title="Agent skills",
        description="Attach skill/tool packs when enabled for proxy requests.",
    ),
    ProxyStepDefinition(
        id=MergedDocsStepMeta.id,
        icon=MergedDocsStepMeta.icon,
        title=MergedDocsStepMeta.title,
        description=MergedDocsStepMeta.description,
    ),
    ProxyStepDefinition(
        id=WebSupplementStepMeta.id,
        icon=WebSupplementStepMeta.icon,
        title=WebSupplementStepMeta.title,
        description=WebSupplementStepMeta.description,
    ),
    ProxyStepDefinition(
        id="kw_trigger",
        icon="key",
        title="Freshness trigger",
        description="Activate web supplement on freshness/release keyword triggers.",
    ),
    ProxyStepDefinition(
        id="fw_trigger",
        icon="help",
        title="Framework trigger",
        description="Activate web supplement when framework confidence is low.",
    ),
    ProxyStepDefinition(
        id="news",
        icon="newspaper",
        title="+ DDG news",
        description="Include DuckDuckGo news snippets when enabled.",
    ),
    ProxyStepDefinition(
        id="excerpt",
        icon="description",
        title="+ Page excerpt",
        description="Allow one full page excerpt fetch from an allowed host.",
    ),
    ProxyStepDefinition(
        id="wiki",
        icon="menu_book",
        title="+ Wikipedia",
        description="Use Wikipedia fallback when DDG snippets are empty.",
    ),
)

_BY_ID: dict[str, ProxyStepDefinition] = {step.id: step for step in _PROXY_PIPELINE_STEPS}


def get_proxy_pipeline_definition() -> list[dict[str, Any]]:
    """Return LLM proxy pipeline step definitions for Web UI."""
    return [
        {
            "id": step.id,
            "icon": step.icon,
            "title": step.title,
            "description": step.description,
        }
        for step in _PROXY_PIPELINE_STEPS
    ]


def get_proxy_pipeline_step_meta(step_id: str) -> dict[str, str] | None:
    """Get metadata for one step id or None when id is unknown."""
    step = _BY_ID.get(step_id)
    if step is None:
        return None
    return {
        "id": step.id,
        "icon": step.icon,
        "title": step.title,
        "description": step.description,
    }


__all__ = ["ProxyStepDefinition", "get_proxy_pipeline_definition", "get_proxy_pipeline_step_meta"]
