"""Tests for rag_service.core.engine."""

from __future__ import annotations

from rag_service.core.contracts import StepResult
from rag_service.core.engine import PipelineExecutionError, RagCore
from rag_service.core.registry import StepRegistry


class _Step:
    def __init__(
        self,
        *,
        step_id: str,
        depends_on: tuple[str, ...] = (),
        enabled_flag: bool = True,
        should_fail: bool = False,
        stop: bool = False,
    ) -> None:
        self.id = step_id
        self.icon = "extension"
        self.title = step_id
        self.description = f"step {step_id}"
        self.depends_on = depends_on
        self._enabled_flag = enabled_flag
        self._should_fail = should_fail
        self._stop = stop

    def enabled(self, config: dict[str, object], ctx: dict[str, object]) -> bool:
        assert "request" in ctx
        if config.get("force_disable") == self.id:
            return False
        return self._enabled_flag

    def run(self, ctx: dict[str, object]) -> StepResult:
        if self._should_fail:
            raise RuntimeError(f"{self.id} failed")
        return StepResult(
            context_updates={f"{self.id}_done": True},
            artifacts={"ok": True},
            stop_pipeline=self._stop,
        )


def test_engine_runs_steps_and_collects_trace() -> None:
    reg = StepRegistry()
    reg.register(_Step(step_id="query_prep"))
    reg.register(_Step(step_id="embed_search_pass1", depends_on=("query_prep",)))
    core = RagCore(reg)

    out = core.run_pipeline(request={"messages": [{"role": "user", "content": "hi"}]})

    assert out.context["query_prep_done"] is True
    assert out.context["embed_search_pass1_done"] is True
    assert out.artifacts["query_prep"]["ok"] is True
    assert [t.status for t in out.trace] == ["executed", "executed"]
    assert [t.id for t in core.get_last_trace()] == ["query_prep", "embed_search_pass1"]


def test_engine_marks_disabled_step() -> None:
    reg = StepRegistry()
    reg.register(_Step(step_id="query_prep", enabled_flag=False))
    core = RagCore(reg)

    out = core.run_pipeline(request={"messages": []})
    assert len(out.trace) == 1
    assert out.trace[0].status == "disabled"


def test_engine_skips_step_when_dependency_not_successful() -> None:
    reg = StepRegistry()
    reg.register(_Step(step_id="query_prep", enabled_flag=False))
    reg.register(_Step(step_id="rerank", depends_on=("query_prep",)))
    core = RagCore(reg)

    out = core.run_pipeline(request={"messages": []})
    assert [t.status for t in out.trace] == ["disabled", "skipped"]


def test_engine_raises_pipeline_execution_error() -> None:
    reg = StepRegistry()
    reg.register(_Step(step_id="query_prep"))
    reg.register(_Step(step_id="rerank", depends_on=("query_prep",), should_fail=True))
    core = RagCore(reg)

    try:
        core.run_pipeline(request={"messages": []})
        assert False, "Expected PipelineExecutionError"
    except PipelineExecutionError as e:
        assert e.step_id == "rerank"
        assert e.trace[-1].status == "failed"
