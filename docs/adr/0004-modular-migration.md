# ADR 0004: Modular Migration — Core vs. CoreModules

## Status

Accepted

## Context

The repository originally mixed host composition, reusable modules, extension payloads, and runtime data at the repository root. This made ownership unclear: a change in a root-level `api/` folder could affect both the monolith and a reusable module, and new code tended to land wherever was convenient. We needed a migration strategy that:

- Keeps the host monolith under a single, explicit container.
- Promotes genuinely reusable modules to their own packages.
- Prevents root-level runtime packages from reappearing.

## Decision

We split the repository into three ownership buckets:

1. **`Core/`** — the application host container:
   - Composition root and legacy monolith tail.
   - Host-owned layers: `api/`, `application/`, `domain/`, `infrastructure/`, `config/`.
   - Shared `core/` contracts/config package.
   - Host-owned services under `Core/modules/` (e.g., `webui_backend`, `prompts_manager`).
2. **`CoreModules/`** — explicit reusable modules/apps that the host depends on:
   - `CoreUI` (React/Vite SPA)
   - `LlmProxy` (OpenAI compatibility)
   - `RagService` (retrieval/RAG engine)
   - `DockerManager`, `LogsManager`, etc.
   - A module must have a clear public responsibility to live here; `CoreModules/` is not a dumping ground.
3. **`extensions/`** — extension payloads managed through extension contracts.

Migration rules:

- Host-owned top-level runtime folders move under `Core/`.
- Reusable modules move to `CoreModules/` only when they have a stable public contract.
- New top-level directories must be classified in `scripts/root_layout_guard.py` before they are added.
- Modules must not import each other's implementations; they communicate through `Core/core/contracts/` and HTTP.

Target data flow:

```text
CoreUI → HTTP → webui_backend → HTTP contracts → RagService
                                          → md_ingestion_service
                                          → crawler_service
```

## Consequences

- **Positive:**
  - Ownership is explicit in code structure.
  - The root layout guard rejects unclassified directories automatically.
  - Reusable modules can be developed and tested with a smaller dependency cone.
- **Negative:**
  - Migration required updating imports, `pyproject.toml` pythonpath, and test paths.
  - Some modules still coexist with the monolith until extraction is complete.
- **Neutral:**
  - `docs/legacy_map.md` tracks remaining intentional tails and their owners.

## References

- `AI_RULES.md` sections 1, 2, and 6
- `docs/MODULAR_STRUCTURE.md`
- `docs/legacy_map.md`
- `scripts/root_layout_guard.py`
