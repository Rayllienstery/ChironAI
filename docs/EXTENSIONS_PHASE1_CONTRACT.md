# Extensions Phase 1 Contract Lock

Phase 1 locks the architecture and contracts for the `0.5.0` Extensions GitHub migration. It does not implement the runtime migration yet; it defines the boundaries and acceptance rules that implementation must obey.

## Target Release

- Completed migration release: `0.5.0`.
- Current planning/contract work remains on the `0.4.x` line until implementation is complete.

## Ownership Boundary

Extensions ownership moves outside the core app.

| Area | Owner |
|------|-------|
| Registry URL, registry polling, registry cache | `modules/extensions_backend` |
| GitHub README/release/tag/ref metadata | `modules/extensions_backend` |
| Install/update/remove/rollback/purge lifecycle | `modules/extensions_backend` |
| Local install state and provenance | `modules/extensions_backend` |
| Blocklist and marketplace policy | `modules/extensions_backend` |
| Extension runtime status polling | `modules/extensions_backend` |
| Host capabilities, provider runtime bridge, sandbox protocol | `CoreModules/ExtensionsHost` target |
| Out-of-process worker isolation | `CoreModules/ExtensionsSandbox` |
| Shared DTOs and HTTP constants | `core/contracts/extensions_api.py` |

Core modules must not poll the registry, GitHub repositories, or extension directories directly. They consume extension state through contracts.

## Target Data Flow

```text
CoreUI -> WebUIBackend -> extensions_backend -> ExtensionsHost -> sandboxed extension worker
LlmProxy -> provider runtime contract -> ExtensionsHost -> sandboxed extension provider
extensions_backend -> ChironAI Extensions Registry -> extension GitHub repositories
```

The current direct wiring through `api/http/*`, `llm_proxy_wiring.py`, `CoreModules/LlmInteractor`, and local `extensions/bundled` scanning is migration tail only.

## API Contract

The shared target DTOs live in:

- `core/contracts/extensions_api.py`

The contract defines:

- API prefixes:
  - `EXTENSIONS_API_PREFIX = "/api/extensions"`
  - `WEBUI_EXTENSIONS_PROXY_PREFIX = "/api/webui/extensions"`
- registry DTOs;
- repository version/README/details DTOs;
- install target and provenance DTOs;
- installed extension and lifecycle DTOs;
- runtime status DTOs;
- tab/provider catalog DTOs;
- security scan/blocklist DTOs.

The WebUI `/api/webui/extensions/*` surface may proxy this contract during migration, but the source of truth is `extensions_backend`.

## Registry Contract

The registry repository is named:

- `ChironAI Extensions Registry`
- recommended slug: `ChironAI-Extensions-Registry`

Registry entries store repository metadata, not version lists.

Required entry fields:

- `id`
- `title`
- `description`
- `repository`
- `visibility`
- `compatibility.extension_api_version`
- `compatibility.app`

Recommended entry fields:

- `icon`
- `homepage`
- `license`
- `publisher`
- `publisher_url`
- `repository_id`
- `tags`
- `min_app_version`
- `max_app_version`
- declared capabilities/permissions

Registry invariants:

- no central `latest_version` list in the GitHub registry;
- available versions are fetched from each extension repository;
- stable installs resolve to immutable release assets or tag archives;
- branch/ref installs are advanced, weak-provenance installs;
- unsupported repository domains/orgs are rejected unless allowlisted;
- repository identity and publisher identity changes require manual review;
- confusing ids/names are rejected.

## Repository Metadata

`extensions_backend` fetches and caches:

- README content;
- releases and tags;
- selected ref manifest preview;
- archive URL;
- resolved commit SHA when available;
- digest/signature/attestation metadata when available.

GitHub API tokens are server-side only. CoreUI never receives them.

Metadata failure is degraded UX, not app startup failure.

## Install And Update Semantics

Install/update uses staging:

1. Resolve target release/tag/branch/commit.
2. Download to staging directory.
3. Validate archive safety.
4. Load and validate `chironai-extension.json`.
5. Validate manifest id and version/ref expectations.
6. Verify digest/signature/attestation when available and required by policy.
7. Run security scan.
8. Compare capability expansion against previous version.
9. Require user consent for high-risk capability expansion.
10. Atomically activate the new runtime generation.

The previous safe version remains available until activation succeeds.

Install state must record:

- repository URL;
- repository id when available;
- selected release/tag/branch/ref;
- resolved commit SHA when available;
- archive URL;
- digest/provenance level;
- manifest version;
- installed timestamp;
- security scan result;
- blocklist status;
- active runtime generation.

## Hot-Plug Runtime

Normal lifecycle actions must not require a full project reload:

- install;
- update;
- enable;
- disable;
- remove;
- rollback;
- restart sandbox;
- kill sandbox.

Targeted reload uses generation snapshots:

- build next provider/tabs/assets generation;
- validate it;
- atomically swap active generation;
- keep or roll back to previous generation on failure.

Responses should include:

- `restart_required`;
- `restart_scope`: `none`, `extension`, `provider_registry`, `backend`, or `app`;
- `runtime_generation`;
- user-facing diagnostic message.

Full app restart is a fallback only for core contract changes that cannot be applied safely at runtime.

## Security And Policy

Security scanning is mandatory before activation.

Scan coverage:

- manifest URL/path safety;
- backend Python risk;
- Docker contract violations;
- dynamic code execution;
- shell launchers;
- download-and-execute chains;
- encoded payloads;
- dependency manifests and lockfiles;
- secret patterns;
- dependency vulnerability metadata when available.

Policy requirements:

- blocklist enforcement on startup, install, update, enable, and targeted reload;
- durable security block across restarts;
- deny-by-default host capabilities;
- capability-scoped `host_context`;
- auditable high-risk host calls;
- no GitHub token exposure to CoreUI, logs, notifications, extensions, or `host_context`.

Publisher states:

- `official`
- `trusted`
- `community`
- `experimental`
- `blocked`
- `unknown`

Capability expansion is a consent event.

## UI Contract

The extension details modal is the install surface.

Header must show:

- icon;
- title;
- publisher/trust state;
- selected version;
- provenance level;
- install/update status;
- primary Install/Update action.

Details must show:

- sanitized README;
- version dropdown from repository releases/tags;
- advanced branch/tag/commit ref override;
- capability/permission badges;
- publisher/repository identity;
- digest/signature/attestation status;
- branch/ref weak-provenance warning;
- README fetch and metadata fetch diagnostics.

README rendering must sanitize raw HTML, scripts, unsafe links, unsafe images, event handlers, and layout-breaking content.

## Notifications

Extensions use Notifications center for:

- registry load failure/recovery;
- download/install/update/remove/enable/disable/rollback;
- sandbox crash/timeout/protocol error/manual stop/restart/block;
- security scan block;
- blocklist disablement;
- capability-expansion consent;
- extension-owned long-running processing;
- service actions.

Crash loops and repeated security/sandbox failures must be rate-limited and aggregated.

## Data Ownership

Remove, disable, rollback, and purge data are distinct operations.

Extension-owned resources must be declared:

- containers;
- volumes;
- settings/secrets;
- logs;
- model caches;
- user data.

User data is not deleted without explicit confirmation.

## Bundled Extension Policy

Bundled extensions may remain only as trusted bootstrap/offline copies.

The source of truth after extraction is the extension's own repository.

Bundled manifest versions must align with the latest approved repository release before publishing.

## Registry Schema Validation Plan

The registry repository should contain:

```text
extensions.json
schemas/registry.schema.json
scripts/validate_registry.py
.github/workflows/validate.yml
```

Validation must check:

- required fields;
- allowed visibility/trust states;
- allowed repository domains/orgs;
- stable repository identity;
- duplicate/confusing ids and names;
- unsupported central version lists;
- compatibility fields;
- declared capabilities;
- branch/ref defaults;
- weak provenance metadata;
- capability expansion review flags;
- blocklist entries.

## Guardrail Tests

Implementation should add guardrails for:

- core/API/LlmProxy direct imports of `extensions_backend` implementations;
- core/API/LlmProxy direct scanning of extension folders;
- direct registry/GitHub polling outside `extensions_backend`;
- frontend bundle token leaks;
- blocklist enforcement across startup and offline local cache;
- generation-based reload rollback;
- repeated notification aggregation.

## Phase 1 Status

- [x] Target module boundary defined.
- [x] Extension API contract defined in `core/contracts/extensions_api.py`.
- [x] Registry fields and invariants documented.
- [x] Repository-backed README/version discovery documented.
- [x] Install provenance, atomic update, rollback, and blocked-extension state documented.
- [x] README sanitization and capability/permission preview documented.
- [x] Publisher trust, blocklist, name-squatting checks, and capability-expansion consent documented.
- [x] Red-team guardrails documented.
- [x] Registry URL configuration ownership decided: `extensions_backend`.
- [x] Checksum/provenance policy decided: required for public/semi-public stable marketplace; weaker provenance must be visible and policy-gated.
- [x] Bundled extension policy decided: trusted bootstrap/offline copies only.
- [x] Registry schema validation plan documented.
