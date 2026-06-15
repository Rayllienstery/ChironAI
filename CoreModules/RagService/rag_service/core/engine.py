"""Execution engine for modular RAG pipelines."""

from __future__ import annotations

import time
from typing import Any, Mapping

from error_manager.exceptions import PipelineError

from rag_service.core.contracts import PipelineRunResult, PipelineTraceStep, StepDefinition
from rag_service.core.registry import StepRegistry


class PipelineExecutionError(PipelineError):
    """Raised when a pipeline step fails and ``continue_on_error=False``.

    Subclasses :class:`error_manager.PipelineError` so callers can catch either
    name. Existing ``raise PipelineExecutionError(step_id, trace, cause)`` call
    sites are preserved via positional arguments.
    """

    def __init__(self, step_id: str, trace: list[PipelineTraceStep], cause: Exception) -> None:
        super().__init__(
            f"pipeline step '{step_id}' failed: {cause}",
            cause=cause,
        )
        self.step_id = step_id
        self.trace = trace
        self.cause = cause


class RagCore:
    """Core orchestrator: registry-backed execution + UI definition payload."""

    def __init__(self, registry: StepRegistry) -> None:
        self._registry = registry
        self._last_trace: list[PipelineTraceStep] = []

    def get_pipeline_definition(self) -> list[StepDefinition]:
        return self._registry.definitions()

    def get_last_trace(self) -> list[PipelineTraceStep]:
        return list(self._last_trace)

    def run_pipeline(
        self,
        *,
        request: dict[str, Any],
        config: Mapping[str, Any] | None = None,
        initial_context: Mapping[str, Any] | None = None,
        continue_on_error: bool = False,
    ) -> PipelineRunResult:
        cfg = dict(config or {})
        ctx: dict[str, Any] = {"request": dict(request)}
        if initial_context:
            ctx.update(dict(initial_context))
        artifacts: dict[str, dict[str, Any]] = {}
        trace: list[PipelineTraceStep] = []
        executed_success: set[str] = set()

        for step in self._registry.ordered_steps():
            deps = tuple(getattr(step, "depends_on", ()) or ())
            if any(dep not in executed_success for dep in deps):
                trace.append(
                    PipelineTraceStep(
                        id=step.id,
                        title=step.title,
                        icon=step.icon,
                        description=step.description,
                        status="skipped",
                        duration_ms=0,
                        error=f"missing successful dependency: {deps}",
                    )
                )
                continue

            try:
                enabled = bool(step.enabled(cfg, ctx))
            except Exception as exc:
                trace.append(
                    PipelineTraceStep(
                        id=step.id,
                        title=step.title,
                        icon=step.icon,
                        description=step.description,
                        status="failed",
                        duration_ms=0,
                        error=f"enabled() failed: {exc}",
                    )
                )
                self._last_trace = trace
                if continue_on_error:
                    continue
                raise PipelineExecutionError(step.id, trace, exc) from exc

            if not enabled:
                trace.append(
                    PipelineTraceStep(
                        id=step.id,
                        title=step.title,
                        icon=step.icon,
                        description=step.description,
                        status="disabled",
                        duration_ms=0,
                        error=None,
                    )
                )
                continue

            t0 = time.perf_counter()
            try:
                result = step.run(ctx)
                duration_ms = int((time.perf_counter() - t0) * 1000)
                if result.context_updates:
                    ctx.update(result.context_updates)
                artifacts[step.id] = dict(result.artifacts or {})
                trace.append(
                    PipelineTraceStep(
                        id=step.id,
                        title=step.title,
                        icon=step.icon,
                        description=step.description,
                        status="executed",
                        duration_ms=duration_ms,
                    )
                )
                executed_success.add(step.id)
                if result.stop_pipeline:
                    break
            except Exception as exc:
                duration_ms = int((time.perf_counter() - t0) * 1000)
                trace.append(
                    PipelineTraceStep(
                        id=step.id,
                        title=step.title,
                        icon=step.icon,
                        description=step.description,
                        status="failed",
                        duration_ms=duration_ms,
                        error=str(exc),
                    )
                )
                self._last_trace = trace
                if continue_on_error:
                    continue
                raise PipelineExecutionError(step.id, trace, exc) from exc

        self._last_trace = trace
        return PipelineRunResult(context=ctx, artifacts=artifacts, trace=trace)


__all__ = ["PipelineExecutionError", "RagCore"]
