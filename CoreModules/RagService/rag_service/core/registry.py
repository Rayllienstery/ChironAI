"""Registry for modular RAG steps."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from rag_service.core.contracts import StepDefinition, StepModule


def _non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_step_metadata(step: StepModule) -> None:
    if not _non_empty_text(step.id):
        raise ValueError("step.id must be non-empty")
    if not _non_empty_text(step.icon):
        raise ValueError(f"step '{step.id}' has empty icon")
    if not _non_empty_text(step.title):
        raise ValueError(f"step '{step.id}' has empty title")
    if not _non_empty_text(step.description):
        raise ValueError(f"step '{step.id}' has empty description")
    deps = getattr(step, "depends_on", ())
    if deps is None:
        deps = ()
    if not isinstance(deps, tuple):
        raise ValueError(f"step '{step.id}' depends_on must be tuple[str, ...]")
    for dep in deps:
        if not _non_empty_text(dep):
            raise ValueError(f"step '{step.id}' has invalid dependency id")


class StepRegistry:
    """Mutable step registry with dependency validation and stable order."""

    def __init__(self) -> None:
        self._steps: list[StepModule] = []
        self._by_id: dict[str, StepModule] = {}

    def register(self, step: StepModule, *, replace: bool = False) -> None:
        _validate_step_metadata(step)
        sid = step.id.strip()
        if sid in self._by_id and not replace:
            raise ValueError(f"step id '{sid}' is already registered")
        if sid in self._by_id and replace:
            self._steps = [s for s in self._steps if s.id != sid]
        self._steps.append(step)
        self._by_id[sid] = step

    def register_many(self, steps: Iterable[StepModule], *, replace: bool = False) -> None:
        for step in steps:
            self.register(step, replace=replace)

    def get(self, step_id: str) -> StepModule | None:
        return self._by_id.get(step_id)

    def require(self, step_id: str) -> StepModule:
        step = self.get(step_id)
        if step is None:
            raise KeyError(f"step '{step_id}' is not registered")
        return step

    def definitions(self) -> list[StepDefinition]:
        return [
            StepDefinition(
                id=s.id,
                icon=s.icon,
                title=s.title,
                description=s.description,
                depends_on=getattr(s, "depends_on", ()) or (),
            )
            for s in self._steps
        ]

    def validate_dependencies(self) -> None:
        known = {s.id for s in self._steps}
        for s in self._steps:
            for dep in (getattr(s, "depends_on", ()) or ()):
                if dep not in known:
                    raise ValueError(f"step '{s.id}' depends on unknown step '{dep}'")

    def ordered_steps(self) -> list[StepModule]:
        """
        Return deterministic topological order.

        If order is ambiguous, preserves registration order.
        """
        self.validate_dependencies()
        index = {s.id: i for i, s in enumerate(self._steps)}
        deps: dict[str, set[str]] = {
            s.id: set((getattr(s, "depends_on", ()) or ())) for s in self._steps
        }
        ordered: list[StepModule] = []
        pending = set(deps.keys())
        while pending:
            ready = sorted(
                [sid for sid in pending if not deps[sid]],
                key=lambda sid: index[sid],
            )
            if not ready:
                cycle = ", ".join(sorted(pending))
                raise ValueError(f"cyclic step dependencies detected: {cycle}")
            for sid in ready:
                ordered.append(self._by_id[sid])
                pending.remove(sid)
                for other in pending:
                    deps[other].discard(sid)
        return ordered


__all__ = ["StepRegistry"]
