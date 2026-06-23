"""Tests for rag_service.core.registry."""

from __future__ import annotations

from rag_service.core.contracts import StepResult
from rag_service.core.registry import StepRegistry


class _StubStep:
    def __init__(
        self,
        *,
        step_id: str,
        icon: str = "database",
        title: str = "Stub",
        description: str = "Stub step",
        depends_on: tuple[str, ...] = (),
    ) -> None:
        self.id = step_id
        self.icon = icon
        self.title = title
        self.description = description
        self.depends_on = depends_on

    def enabled(self, config: dict[str, object], ctx: dict[str, object]) -> bool:
        assert config is not None
        assert ctx is not None
        return True

    def run(self, ctx: dict[str, object]) -> StepResult:
        return StepResult()


def test_registry_rejects_missing_icon() -> None:
    reg = StepRegistry()
    step = _StubStep(step_id="query_prep", icon=" ")
    try:
        reg.register(step)
        assert False, "Expected ValueError for empty icon"
    except ValueError as e:
        assert "empty icon" in str(e)


def test_registry_rejects_duplicate_id() -> None:
    reg = StepRegistry()
    reg.register(_StubStep(step_id="query_prep"))
    try:
        reg.register(_StubStep(step_id="query_prep"))
        assert False, "Expected ValueError for duplicate id"
    except ValueError as e:
        assert "already registered" in str(e)


def test_registry_validates_unknown_dependency() -> None:
    reg = StepRegistry()
    reg.register(_StubStep(step_id="rerank", depends_on=("embed_search_pass1",)))
    try:
        reg.validate_dependencies()
        assert False, "Expected ValueError for unknown dependency"
    except ValueError as e:
        assert "unknown step" in str(e)


def test_registry_topological_order() -> None:
    reg = StepRegistry()
    reg.register(_StubStep(step_id="context_assembly", depends_on=("rerank",)))
    reg.register(_StubStep(step_id="query_prep"))
    reg.register(_StubStep(step_id="rerank", depends_on=("query_prep",)))

    ordered = [s.id for s in reg.ordered_steps()]
    assert ordered == ["query_prep", "rerank", "context_assembly"]
