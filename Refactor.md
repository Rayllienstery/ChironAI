# Refactor Plan: No Freelance Runtime Code

## Purpose

The goal of this refactor is not to move every folder into `CoreModules`.
The goal is to remove root-level runtime "freelancers": code that is required
for startup or behavior, but has no obvious owner, boundary, or reason to live
at the repository root.

Every runtime dependency must belong to one of these ownership buckets:

- `Core/`: the application host, composition root, legacy monolith tail,
  shared contracts/config, and services that are part of the main app runtime.
- `CoreModules/`: explicit reusable modules and applications that the host
  depends on, such as `CoreUI`, `LlmProxy`, `RagService`, `DockerManager`, and
  `LogsManager`.
- `extensions/`: installed or bundled extension payloads, owned through the
  extension contracts and extension-management backend.
- non-runtime project support: `docs/`, `tests/`, `scripts/`, `.github/`,
  config files, generated/runtime data folders, and temporary/dev-only folders.

If a folder is required for the app to start, it must not live in the root as an
unowned standalone directory.

## Target Repository Shape

```text
Core/
  api/                  # host HTTP composition and legacy route tail
  application/          # host application use cases
  domain/               # host domain model and ports
  infrastructure/       # host adapters and compatibility shims
  config/               # host configuration authority
  core/                 # shared contracts/config package; import name stays `core`
  modules/              # host-owned services that are not CoreModules
    webui_backend/
    extensions_backend/
    crawler_service/
    html_md/
    md_indexer/
    tools/

CoreModules/
  CoreUI/
  DockerManager/
  ErrorManager/
  ExtensionsSandbox/
  LlmInteractor/
  LlmProxy/
  LogsManager/
  MdIngestionService/
  RagService/
  ...

extensions/
docs/
scripts/
tests/
WebUI/                  # runtime/data folder, not frontend source
logs/
tmp/
```

Notes:

- The Python import names do not need to change in the first pass. The repo can
  add `Core/` and `Core/modules/*` to `PYTHONPATH` so imports like `api`,
  `application`, `domain`, `infrastructure`, `config`, `core`,
  `webui_backend`, and `extensions_backend` keep working.
- `CoreModules/` is not a dumping ground. A package belongs there only when it
  is a named reusable module with its own responsibility, tests, and boundary.
- `Core/core/` may keep the import name `core` to avoid a high-risk rename of
  shared contracts and config.

## Ownership Rules

1. Every runtime folder must have a documented owner and purpose.
2. Any code needed at startup must live under `Core/`, `CoreModules/`, or the
   extension system.
3. New root-level runtime packages are forbidden unless they are explicitly
   added to an allowlist with a documented reason.
4. Moving code must preserve dependency direction:
   - `domain` remains inner-layer code.
   - host routes compose use cases and contracts; they do not become feature
     dumping grounds.
   - modules communicate through `core/contracts/*`, stable Python protocols,
     or HTTP contracts.
5. UI source stays in `CoreModules/CoreUI` unless it is extension-owned UI using
   the supported extension integration points.

## Phase 0. Inventory and Root Allowlist

**Goal:** identify which root entries are runtime code, runtime data, project
support, or temporary/dev-only material.

### Tasks

1. Produce a root ownership table for every top-level folder.
2. Classify each folder as `Core`, `CoreModule`, `extension`, `runtime data`,
   `project support`, or `temporary`.
3. Add a root-layout guardrail test or script that fails when a new runtime
   package appears at the root without an allowlist entry.
4. Document allowed root folders in `AI_RULES.md` and `docs/MODULAR_STRUCTURE.md`.

### Acceptance Criteria

- [x] Every root folder has an owner classification.
- [x] New unowned root runtime folders are rejected by an automated guardrail.
- [x] The allowlist distinguishes source code from runtime data.

## Phase 1. Introduce `Core/` Container Without Import Renames

**Goal:** move host-owned root runtime folders into `Core/` while keeping public
Python import names stable.

### Initial Move Set

- `api/` -> `Core/api/`
- `application/` -> `Core/application/`
- `domain/` -> `Core/domain/`
- `infrastructure/` -> `Core/infrastructure/`
- `config/` -> `Core/config/`
- `core/` -> `Core/core/`

### Tasks

1. Create the `Core/` directory and move the host-owned folders.
2. Update `pyproject.toml`, pytest `pythonpath`, ruff/vulture paths, packaging
   package-dir entries, and local launch scripts so old import names still
   resolve.
3. Update docs and references that describe the physical paths.
4. Run focused import/startup checks.

### Acceptance Criteria

- [x] The moved packages no longer live at the repository root.
- [x] Existing import names still work.
- [x] Import-linter domain boundary still passes or any known gap is documented.
- [x] API route composition imports successfully.
- [x] App startup path is verified through `build_and_run.bat` if any non-md
      files changed.

## Phase 2. Move Host-Owned `modules/` Under `Core/modules/`

**Goal:** remove the top-level `modules/` folder without misclassifying all
services as CoreModules.

### Default Move Set

- `modules/webui_backend` -> `Core/modules/webui_backend`
- `modules/extensions_backend` -> `Core/modules/extensions_backend`
- `modules/crawler_service` -> `Core/modules/crawler_service`
- `modules/html_md` -> `Core/modules/html_md`
- `modules/md_indexer` -> `Core/modules/md_indexer`
- `modules/tools` -> `Core/modules/tools`

### Tasks

1. Confirm each module's owner and runtime role before moving it.
2. Move host-owned modules into `Core/modules/`.
3. Update package-dir entries, pytest pythonpath, ruff/vulture paths, scripts,
   docs, and tests.
4. Keep module import names stable where possible.
5. Decide separately whether any module deserves promotion to `CoreModules/`.

### Acceptance Criteria

- [x] There is no top-level `modules/` source folder.
- [x] `webui_backend` remains the canonical Web UI backend package.
- [x] `extensions_backend` remains the owner of registry/discovery/install/status.
- [x] No module is promoted to `CoreModules/` without a documented module
      contract and responsibility.

## Phase 3. Prompt Ownership

**Goal:** remove `prompts/` as a root-level runtime data/code dependency.

### Preferred Direction

Create a small prompt ownership layer instead of only moving files:

- either `Core/modules/prompts_manager/` if prompts are app-host data, or
- `CoreModules/PromptsManager/` if prompt management becomes a reusable module.

### Tasks

1. Decide whether prompt templates are host-owned app data or a reusable
   CoreModule.
2. Move prompt files under the chosen owner.
3. Keep a compatibility facade for `config.rag_prompts` until call sites are
   migrated.
4. Update `/api/webui/prompts`, CoreUI prompt selectors, RAG tests, config docs,
   and OpenAPI docs.
5. Add migration/backward-compatibility handling for existing local prompt files.

### Acceptance Criteria

- [ ] `prompts/` no longer lives as an unowned root runtime dependency.
- [ ] Prompt listing, loading, creation, trash, restore, and preview still work.
- [ ] Existing `RAG_PROMPT` and `rag.prompt` behavior is preserved.
- [ ] Prompt storage owner is documented.

## Phase 4. Extension Host Boundary Cleanup

**Goal:** make extension ownership explicit and avoid hidden direct dependencies.

### Tasks

1. Keep registry/discovery/install/status ownership in `extensions_backend`.
2. Keep sandbox worker isolation in `CoreModules/ExtensionsSandbox`.
3. Introduce or complete `CoreModules/ExtensionsHost` only for host/runtime
   contracts and capability bridge code.
4. Remove direct registry, bundled-extension, or install-state probing from
   unrelated core/API/proxy code.

### Acceptance Criteria

- [ ] Extension marketplace state is owned by `extensions_backend`.
- [ ] CoreModules consume extension state through contracts.
- [ ] No direct Docker or registry polling appears outside the documented owner.

## Phase 5. Legacy Tail Reduction by Owner

**Goal:** reduce legacy root/host code by bounded context, not by folder name.

### Tasks

1. Pick one bounded context at a time: WebUI routes, RAG tests, crawler/indexer,
   settings, service control, provider runtime, or prompt templates.
2. Move behavior toward the documented owner.
3. Replace concrete cross-imports with contracts or thin compatibility facades.
4. Update `docs/legacy_map.md` when a tail is reduced or intentionally kept.

### Acceptance Criteria

- [ ] Every remaining legacy tail has an owner and reason.
- [ ] No new unowned root-level code is introduced.
- [ ] Tests cover the migrated contract boundary.

## Guardrails to Add

- Root source allowlist test: rejects unapproved runtime package folders at repo
  root.
- Import smoke test: verifies `api`, `application`, `domain`, `infrastructure`,
  `config`, `core`, `webui_backend`, and `extensions_backend` import after
  physical moves.
- Dependency boundary test: keeps `domain` from importing outer layers.
- Docs sync check: requires `AI_RULES.md` and `docs/MODULAR_STRUCTURE.md` to
  mention any newly approved root runtime folder.

## What Not To Do

- Do not move all `modules/*` into `CoreModules/` just to clean the root.
- Do not scatter CoreUI components into backend modules. CoreUI remains the UI
  source of truth.
- Do not rename public Python import packages in the same pass as physical
  folder moves.
- Do not leave compatibility shims undocumented.
- Do not keep a startup dependency in root because "it works there"; assign an
  owner or move it.
