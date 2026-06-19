# ADR 0001: Layered Architecture for the ChironAI Host

## Status

Accepted

## Context

ChironAI started as a monolithic Flask application with routes, business logic, domain rules, and infrastructure concerns mixed in the same modules. As the product grew, the codebase accumulated hidden dependencies: API handlers called Qdrant directly, domain modules imported Flask request contexts, and infrastructure code made UI-level decisions. We needed a stable structural contract that:

- Makes the boundary between HTTP surface, application orchestration, domain rules, and infrastructure explicit.
- Allows us to extract reusable modules (`CoreModules/`) without dragging the monolith along.
- Can be enforced automatically by import-linter and reviewed by humans.

## Decision

We adopt a strict layered architecture for the host code under `Core/`:

```text
Core/api/           → HTTP/CLI adapters; only layer that knows Flask/Click
Core/application/   → use-case orchestration; may call domain and infrastructure
Core/domain/        → pure business rules; no imports from api/application/infrastructure
Core/infrastructure/→ I/O, persistence, third-party clients; no imports from api/application
Core/config/        → configuration authority; used by all layers through explicit getters
Core/core/          → shared contracts, constants, and version; may be imported by any layer
```

Key rules:

1. `Core/domain/` is the inner layer. It must not import `api`, `application`, or `infrastructure`. This is enforced by import-linter contract `domain_is_inner_layer`.
2. `Core/application/` must not import `api`.
3. `Core/infrastructure/` must not import `api`.
4. Cross-cutting concerns (logging, correlation IDs, settings resolution) live in `Core/core/` or `Core/config/` and are consumed through thin ports, not by reaching across layers.
5. WebUI route composition is split intentionally: `Core/api/http/service_control.py` handles lifecycle bridges, while `Core/api/http/webui_routes.py` handles HTTP composition. They are not merged back.

## Consequences

- **Positive:**
  - Domain logic can be unit-tested without Flask or Qdrant.
  - Import-linter gives fast, mechanical feedback on architectural violations.
  - Extraction of `CoreModules/` becomes a matter of moving whole layers rather than untangling mixed code.
- **Negative:**
  - Legacy tails required careful refactoring to avoid breaking existing routes and tests.
  - Some previously convenient shortcuts (e.g., domain code reading `request.json`) had to be replaced by explicit parameter passing.
- **Neutral:**
  - The guardrail `scripts/root_layout_guard.py` documents which top-level directories are allowed, preventing new freelance runtime packages at the repository root.

## References

- `AI_RULES.md` section 5
- `docs/ARCHITECTURE.md`
- `pyproject.toml` `[tool.importlinter]` contracts
- `tests/application/test_ollama_migration_guardrails.py`
