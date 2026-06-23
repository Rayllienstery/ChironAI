"""Core contracts for modular RAG pipeline steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping, Protocol


@dataclass(frozen=True)
class StepDefinition:
    """UI-facing metadata for one pipeline step."""

    id: str
    icon: str
    title: str
    description: str
    depends_on: tuple[str, ...] = ()


@dataclass
class StepResult:
    """
    Result of one step execution.

    `context_updates` are merged into shared pipeline context.
    `artifacts` are stored under step id in engine-level artifact map.
    """

    context_updates: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    stop_pipeline: bool = False


@dataclass(frozen=True)
class PipelineTraceStep:
    """One trace entry for executed/disabled/skipped/failed steps."""

    id: str
    title: str
    icon: str
    description: str
    status: str
    duration_ms: int
    error: str | None = None


@dataclass
class PipelineRunResult:
    """Final pipeline execution payload."""

    context: dict[str, Any]
    artifacts: dict[str, dict[str, Any]]
    trace: list[PipelineTraceStep]


class StepModule(Protocol):
    """
    Contract for modular RAG step.

    Every step must provide mandatory UI metadata and behavior hooks.
    """

    id: str
    icon: str
    title: str
    description: str
    depends_on: tuple[str, ...]

    def enabled(self, config: Mapping[str, Any], ctx: Mapping[str, Any]) -> bool:
        """Return whether this step should run for the current request/context."""

    def run(self, ctx: MutableMapping[str, Any]) -> StepResult:
        """Execute step and return step result."""


__all__ = [
    "PipelineRunResult",
    "PipelineTraceStep",
    "StepDefinition",
    "StepModule",
    "StepResult",
]
