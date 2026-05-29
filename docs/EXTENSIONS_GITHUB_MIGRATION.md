# Extensions GitHub Migration Task

## Purpose

Prepare ChironAI Extensions for a repository-based distribution model:

- move the public extension registry from the application repository to a dedicated GitHub repository;
- move each extension from `extensions/bundled/<extension-id>` to its own GitHub repository;
- move extension discovery, registry polling, install/update/remove, and status ownership out of the core app into a dedicated extension-management module;
- keep local development, trusted bundled extensions, installation, security audit, and CoreUI extension management working during the migration.

Target project release for this migration: `0.5.0`.

This document is the planning and acceptance checklist for the migration. It records the target ownership split between the extension-management module and the core extension host/runtime contracts.

## Current State

- The app config now defaults to the GitHub-hosted registry, with `extensions/registry/extensions.json` kept as a local/offline fallback.
- `modules/extensions_backend` owns the registry client, GitHub repository metadata client, blocklist policy, and contract-facing `ExtensionManagementService` facade.
- `ExtensionRegistryClient` can load a registry from a local path, `file://`, `http://`, or `https://`, and records diagnostics when it falls back locally.
- `ExtensionManager.install()` installs from:
  - `source_path` for local repository paths;
  - `archive_url`;
  - GitHub release assets and GitHub branch/tag archive URLs resolved from repository metadata.
- Bundled extensions are auto-installed from `extensions/bundled` as trusted bootstrap/offline copies only.
- Installed extension payloads are copied to `logs/extensions/installed/<extension-id>/<version>`.
- Every install is checked by manifest loading and extension security audit.
- Notifications already use `source: "extensions"` for security blocks and sandbox failures through CoreUI's notification center.
- Extension workers already run out-of-process through the sandbox layer, and sandbox workers can be restarted or killed independently.
- Install, enable, disable, and remove attempt a targeted runtime reload and return `reload_status`, `restart_required`, and `restart_scope`.
- The Flask app stores extension state through contract-shaped accessors and exposes API routes through the extension-management facade instead of direct legacy app keys.
- API routes no longer scan bundled extension directories or read extension-manager implementation state directly.
- The extension manifest contract is `chironai-extension.json` with `api_version: "1"` and a required backend entrypoint.
- Existing bundled extensions are:
  - `ollama-provider`
  - `open-webui`
  - `codex-launcher`

Bundled copies are now sync-checked against the extracted extension repositories with `scripts/sync_bundled_extensions.py`; the GitHub registry target avoids central version-list drift by resolving available versions from each extension repository.

## Research Signals

The migration should borrow from established extension marketplaces and software supply-chain guidance:

- VS Code Marketplace-style controls: malware scan every package and update, verified publishers, unusual usage monitoring, name-squatting protection, blocklist removal, signature verification, and secret scanning.
- Browser-store-style controls: show users functionality, publisher, permissions, and data-use information before install; periodically re-review published items; deactivate severe policy violations from the client.
- OWASP/OpenSSF-style supply-chain controls: avoid floating `latest` for activation, verify integrity/provenance, keep immutable artifacts, retain SBOM/security metadata, monitor CVE/OSV sources, sandbox third-party code, and use approved registries.
- GitHub release controls: prefer release assets or GitHub release archives with recorded digest, release metadata, resolved commit SHA, and artifact attestation where available.

These are not optional polish. They shape the acceptance criteria below.

## Red-Team Failure Modes

This migration should be designed as if it will be attacked through maintenance, updates, and shortcuts rather than through the first obvious install path.

### Boundary Drift

Risk: `extensions_backend` exists, but core/API/LlmProxy continue to inspect `extensions/bundled`, registry files, GitHub URLs, or `llm_extensions_service` implementation state directly.

Guardrails:

- Add import-boundary tests that fail if core/API/LlmProxy import `extensions_backend` implementations.
- Add grep/AST guardrails that fail if core/API/LlmProxy scan extension folders directly outside explicitly allowlisted migration-tail code.
- Track all remaining direct extension wiring as migration tail in docs until removed.

### Malicious Update

Risk: a safe extension becomes dangerous through a later release, dependency update, publisher compromise, or capability expansion.

Guardrails:

- Treat update as a consent event when capabilities, Docker/service behavior, settings/secrets, provider scope, network behavior, or data-use declarations change.
- Never auto-activate a new `latest`; always record and activate a concrete version/ref/commit.
- Keep previous safe version available until the new version passes validation and security scanning.

### Publisher And Repository Takeover

Risk: GitHub `owner/name` stays familiar while repository ownership, publisher identity, or release workflow changes.

Guardrails:

- Store stable GitHub repository identity when available, not only URL.
- Store expected publisher identity and trust state.
- Require manual review when ownership, repository identity, publisher identity, release workflow, or high-risk capabilities change.
- Use central blocklist for compromised publisher identities, repos, refs, and versions.

### Registry PR Poisoning

Risk: a malicious registry entry uses a confusing id/name/icon/description, branch ref, or trusted-looking README.

Guardrails:

- Add name-squatting and typo-squatting checks.
- Require review for new publishers and high-risk capabilities.
- Reject unsupported repository domains/orgs unless explicitly allowlisted.
- Warn or block branch/ref installs outside an advanced path.

### Branch/Ref Escape Hatch

Risk: manual branch/ref install bypasses stable release provenance.

Guardrails:

- Hide manual branch/ref install behind an advanced control.
- Resolve and display commit SHA before install.
- Mark branch/ref installs as weaker provenance and exclude them from silent update paths.
- Scan branch/ref payloads exactly like release payloads.

### README And Marketplace UI Abuse

Risk: untrusted README content tricks users, breaks layout, tracks them, or attempts script/link abuse.

Guardrails:

- Sanitize Markdown before rendering.
- Strip raw HTML, scripts, event handlers, unsafe URLs, unsafe images, and layout-breaking content.
- Show external-link warnings for repository/README links.
- Do not allow README fetch failures to hide install provenance or security state.

### Static Scan Blind Spots

Risk: code passes static audit but exfiltrates data at runtime using allowed APIs, network calls, or broad host capabilities.

Guardrails:

- Add runtime permission/capability model for network, filesystem, settings/secrets, Docker/service, model/provider, and log access.
- Deny undeclared capabilities by default.
- Add runtime call auditing for high-risk host calls.
- Consider dynamic/runtime behavior monitoring for later phases.

### Overpowered Host Context

Risk: `host_context` exposes broad callables, so the extension does not need an exploit.

Guardrails:

- Scope `host_context` per extension based on manifest capabilities and user consent.
- Make host calls deny-by-default.
- Require typed, auditable host capabilities instead of arbitrary callables.
- Log denied host calls and surface repeated violations as extension security events.

### GitHub Token Exposure

Risk: GitHub token leaks into CoreUI bundle, browser devtools, logs, README fetch payloads, or extension context.

Guardrails:

- GitHub tokens remain server-side only.
- Add frontend bundle/static tests for `GITHUB_TOKEN`, `Authorization`, `ghp_`, `github_pat_`, and similar token patterns.
- Redact tokens from logs and notifications.
- Do not expose GitHub token through `host_context` or extension metadata.

### Artifact Trust Illusion

Risk: tag archives are treated as fully trusted releases even without digest/signature/attestation.

Guardrails:

- Prefer release assets with digest/signature/attestation evidence.
- Record provenance level: attested release asset, digest-only release asset, GitHub tag archive, branch/ref archive.
- Show provenance level in CoreUI before install.
- Require stronger review for weak-provenance installs.

### Blocklist Freshness

Risk: blocklist exists but is stale, cached too long, or not enforced on startup.

Guardrails:

- Keep blocklist separate from extension metadata or clearly versioned inside registry metadata.
- Use short TTL plus last-known-good local cache.
- Enforce blocklist on startup, targeted reload, install, update, and enable.
- Notify users when an installed extension is disabled by blocklist or policy.

### Hot Reload Race

Risk: extension install/update/remove rebuilds provider registry while LlmProxy or CoreUI is using old runtime state.

Guardrails:

- Use generation-based runtime snapshots.
- Build and validate the next generation before swapping it into active use.
- Allow in-flight calls to finish or cancel them explicitly with clear errors.
- Roll back to previous generation if targeted reload fails.

### Data Persistence Trap

Risk: removing extension code leaves containers, volumes, logs, settings, tokens, and model caches behind; or deletes user data unexpectedly.

Guardrails:

- Separate disable, remove code, rollback, and purge data.
- Require extension-owned data/resource declarations.
- Require explicit confirmation before deleting user data.
- Keep purge operations observable and recoverable where possible.

### Notification Flood

Risk: a crash loop floods Notifications center and hides important events.

Guardrails:

- Rate-limit extension notifications.
- Aggregate repeated failures with stable aggregation keys.
- Show crash-loop state as one durable notification with counts.
- Suppress repeated identical sandbox/security events after threshold while preserving diagnostics.

### Dependency Bomb

Risk: extension code is clean, but dependency install or update pulls malware.

Guardrails:

- Prefer lockfiles and pinned dependencies.
- Scan dependency manifests and lockfiles.
- Retain SBOM/dependency inventory when practical.
- Do not allow install-time network dependency resolution during activation unless explicitly declared and approved.

## Target State

ChironAI should consume extension metadata from a GitHub-hosted registry, and each registry entry should point to the extension's GitHub repository. Concrete install artifacts are resolved later from the selected release, tag, branch, or commit ref.

Extension ownership must be outside the core app:

- Extension repositories live outside the main ChironAI repository.
- The registry repository lives outside the main ChironAI repository.
- Extension discovery, registry polling, README/version fetching, install/update/remove, local install state, blocklist enforcement, and extension status polling belong to a dedicated extension-management module/service, not to the core app.
- The core app may contain a CoreModule for extension contracts, host capabilities, provider-runtime interfaces, sandbox protocol, and DTOs.
- The core app must not scan extension directories or poll extension availability directly. It asks the extension-management module through a contract.
- LLM Proxy, WebUI backend, CoreUI, and future modules consume extension runtime/status through contracts, not by importing extension-manager implementations.

Recommended target flow:

1. The extension-management module reads registry JSON from a configured URL.
2. Registry entries expose display metadata, compatibility metadata, and the source repository URL.
3. CoreUI opens an extension details modal for not-installed extensions and renders the extension README directly from GitHub before install.
4. The extension-management module resolves available versions from the extension repository, defaults to the latest GitHub release, and still allows an explicit branch/ref override for development or recovery.
5. The extension-management module installs a selected extension version into the managed installed extensions directory.
6. The extension-management module validates the downloaded payload:
   - safe archive extraction;
   - `chironai-extension.json` exists and is valid;
   - manifest id/version match the registry entry;
   - security audit passes;
   - optional checksum/signature verification passes when implemented.
7. The extension-management module activates installs and updates atomically only after validation and security scanning pass.
8. Security scans run on every install and update. If a scan finds blocking issues, the extension is disabled or the previous safe version remains active, and the user receives a dangerous-extension notification.
9. Extension install, update, enable, disable, and remove should not require a full project reload in normal cases. The extension host should apply targeted reloads and keep the Core app running.
10. CoreUI continues to show registry, installed extensions, providers, tabs, sandbox diagnostics, and security findings through `/api/webui/extensions/*`.
11. Extension lifecycle and processing events are visible in the Notifications center, including downloads, installs, removals, updates, runtime startup, sandbox failures, security blocks, and extension-owned processing errors.

## Repository Model

## Target Module Boundary

The migration should introduce a clear split between extension ownership and core runtime contracts.

Recommended target layout:

```text
modules/
  extensions_backend/        # owns registry, repository metadata, install state, lifecycle, status, blocklist
CoreModules/
  ExtensionsHost/            # contracts/runtime facade, host capabilities, sandbox protocol, provider bridge
  ExtensionsSandbox/         # worker isolation implementation, reusable by ExtensionsHost
core/
  contracts/
    extensions_api.py        # HTTP DTOs and constants for CoreUI/WebUIBackend/extensions_backend
```

Naming can be adjusted, but the boundary is not optional:

- `modules/extensions_backend` owns extension discovery and answers "which extensions exist/are installed/are running?".
- `CoreModules/ExtensionsHost` exposes only stable host-side contracts, sandbox/runtime adapters, and capability APIs needed by the rest of the app.
- `CoreModules/ExtensionsHost` must not own GitHub registry polling, repository metadata fetching, or marketplace policy.
- Core modules must not import extension repository code.
- Extensions must not import core app internals. They interact through `host_context`, declared capabilities, and versioned contracts.
- `CoreUI` talks to `/api/webui` or the target WebUI backend; it does not call GitHub or scan local extension folders directly.
- `webui_backend` may proxy extension endpoints, but the source of truth is the extension-management module.
- `LlmProxy` consumes providers through a provider/runtime contract. It must not know where an extension is installed or how the registry works.

Target data flow:

```text
CoreUI -> WebUIBackend -> extensions_backend -> ExtensionsHost/CoreModule -> sandboxed extension worker
LlmProxy -> provider runtime contract -> ExtensionsHost/CoreModule -> sandboxed extension provider
extensions_backend -> GitHub registry/repositories
```

Current direct wiring in `api/http/*`, `llm_proxy_wiring.py`, and `CoreModules/LlmInteractor` should be treated as migration tail until it is replaced by the contract boundary above.

### Registry Repository

Create a dedicated repository named `ChironAI Extensions Registry`.

Recommended GitHub repository slug: `ChironAI-Extensions-Registry`.

Minimum expected content:

```text
extensions.json
schemas/
  registry.schema.json
README.md
CONTRIBUTING.md
```

Recommended later content:

```text
extensions/
  ollama-provider.json
  open-webui.json
  codex-launcher.json
scripts/
  validate_registry.py
.github/workflows/
  validate.yml
```

The registry can start as a single `extensions.json`. Split-per-extension metadata can come later if review noise becomes high.

### Extension Repositories

Create one repository per extension, for example:

- `chironai-extension-ollama-provider`
- `chironai-extension-open-webui`
- `chironai-extension-codex-launcher`

Minimum expected content:

```text
chironai-extension.json
backend/
icons/
README.md
CHANGELOG.md
LICENSE
tests/
.github/workflows/
  validate.yml
```

Each extension repository should be independently buildable, testable, and releasable. It must not depend on files under the main ChironAI repository except through documented extension APIs and host capabilities.

## Registry Entry Contract

The current runtime already accepts legacy local fields such as `source_path`, `archive_url`, `default_ref`, and `latest_version`. Keep them during migration for compatibility with local development and existing tests.

Target GitHub registry entries should be repository-based:

```json
{
  "id": "ollama-provider",
  "title": "Ollama",
  "description": "Trusted local Ollama provider for ChironAI LLM runtime.",
  "icon": "icons/ollama-light.svg",
  "repository": "https://github.com/chironai/chironai-extension-ollama-provider",
  "visibility": "trusted",
  "compatibility": {
    "extension_api_version": "1",
    "app": "chironai"
  }
}
```

Recommended fields to add before relying on the GitHub registry as the main source:

```json
{
  "homepage": "https://github.com/chironai/chironai-extension-ollama-provider",
  "license": "MIT",
  "publisher": "ChironAI",
  "publisher_url": "https://chironai.example",
  "repository_id": "github-node-or-numeric-id",
  "tags": ["llm_provider", "ollama", "local"],
  "min_app_version": "0.4.21",
  "max_app_version": null
}
```

The registry must not store the full version list. It should store the repository location; CoreUI/backend should fetch tags/releases from the specific extension repository when the user opens the details modal or version dropdown.

Default install behavior should use the latest GitHub release. Advanced install behavior may allow:

- selecting a version from a repository-backed dropdown;
- entering a specific branch, tag, or commit ref manually;
- installing a branch/ref with a clear warning that it is not an immutable stable release.

Do not use branch archives such as `main.zip` for stable installs. Stable installs should point to immutable release artifacts or tag archives.

Registry validation must reject unsupported repository URLs. The official registry should accept only expected GitHub repository locations, preferably under the configured ChironAI organization or an explicitly reviewed allowlist.

Registry validation should also protect against ownership drift and name squatting:

- lock each entry to an expected publisher identity;
- store and verify stable GitHub repository identity when available, not only `owner/name`;
- reject confusingly similar extension ids and names;
- require manual review when repository ownership, publisher identity, or high-risk capabilities change.

## Core App Work

### Registry Loading

- Add a configurable registry URL to the extension-management module, with the current local file as a development fallback.
- Prefer explicit configuration over hardcoding a GitHub URL in runtime code.
- Keep support for local `source_path` entries for developer workflows and tests.
- Add diagnostics that show which registry URL was loaded and when it failed.
- Support an emergency blocklist that can disable or hide unsafe extension ids/versions/refs even if they still exist in GitHub.
- Core app and LLM Proxy must not poll the registry directly; they should ask the extension-management module over the extension API contract.

### Install Semantics

- Require the install resolver to produce a concrete archive URL from the selected GitHub release, tag, branch, or commit ref.
- Resolve the default install target from the latest GitHub release for the extension repository.
- Fetch selectable versions from the extension repository, not from the central registry.
- Allow a manually specified branch/tag/commit ref for development, testing, and emergency recovery.
- Validate that the downloaded manifest id equals the selected registry id.
- Validate that the downloaded manifest version equals the selected release/tag version when the install target is versioned. For branch or commit installs, record both the manifest version and the selected ref.
- Add checksum, release asset signature, or GitHub artifact attestation verification before the registry becomes public or semi-public.
- Store provenance for every install: repository URL, selected release/tag/branch/ref, resolved commit SHA when available, archive URL, manifest version, installed timestamp, and security scan result.
- Install and update through a staging directory. Do not overwrite or activate the current version until archive validation, manifest validation, compatibility checks, and security scanning pass.
- Keep the previous safe version available for rollback when an update fails after download or scan.
- Persist enough install history to explain which version/ref is running and why an update was blocked.
- Do not auto-activate a new "latest" silently. The UI may default to the latest release for new installs, but activation must record the concrete selected version/ref and resolved commit.
- Prefer targeted extension reload over full app restart. Full project reload should be a fallback only for core contract changes that cannot be applied safely at runtime.
- Run the security audit on every install and every update before enabling the extension.
- If an update fails security audit, disable the extension or keep the previous safe version active, then notify the user that the new extension payload is unsafe.

### Bundled Extensions

- Decide which extensions remain bundled for offline-first behavior.
- If bundled extensions remain, document that they are trusted bootstrap extensions, not the canonical distribution source.
- Align bundled manifest versions with the latest repository release before publishing.
- Avoid dual ownership: the extension repository should be the source of truth for extension code after extraction.

### Web UI API And CoreUI

- Keep `/api/webui/extensions/registry` response shape compatible with `CoreModules/CoreUI/src/components/ExtensionsTab.jsx`.
- If registry fields are added, update `core/contracts/webui_api.py`, `CoreModules/CoreUI/src/services/api.js`, and route tests together.
- Clicking a not-installed extension card must open a details modal before install.
- The details modal must render the extension README fetched from the GitHub repository.
- The details modal/card header must be a complete install surface: extension icon, title, short description or publisher, selected version, install/update status, and primary Install button.
- The version selector should live in the header area so users can choose a release before installing without hunting through the README.
- The details modal must show install controls: latest release by default, version dropdown from repository releases/tags, and an explicit branch/ref override.
- The selected version in the header, README/details state, and install request payload must stay synchronized.
- The details modal should show capability and permission badges before install, including provider type, `tab_ui`, `iframe_tab`, service actions, Docker host-capability use, settings/secrets, and other high-risk capabilities declared by the selected manifest.
- The details modal should show publisher trust information: publisher name, verified/official/trusted state, repository URL, license, selected ref/release, and whether the selected artifact has digest/signature/attestation evidence.
- The details modal should warn when a selected version adds new capabilities, requests new sensitive settings/secrets, changes service/Docker behavior, or comes from a branch/ref rather than a release.
- The details modal should show provenance level: attested release asset, digest-only release asset, GitHub tag archive, or branch/ref archive.
- Repository README Markdown must be sanitized before rendering. Raw HTML, scripts, unsafe links, unsafe image sources, and layout-breaking content must be blocked or normalized.
- GitHub API tokens, if configured for rate limits or private repos, must stay server-side and must never be exposed to CoreUI.
- GitHub README/version fetches should support caching, stale fallback, rate-limit diagnostics, and offline behavior.
- README fetch failures should not block installation, but they must be visible to the user.
- Surface install failures clearly: download failure, bad archive, manifest mismatch, compatibility failure, checksum failure, and security audit block should be distinguishable.

### Notifications Center

Extension operations must be first-class notification producers. A user should be able to understand what happened to an extension without staying on the Extensions tab.

Required notification coverage:

- Registry load failures and recovery.
- Extension download started, in progress, completed, cancelled, and failed.
- Extension install completed and failed.
- Extension update available, update started, update completed, and update failed.
- Extension enable, disable, remove, and rollback completed or failed.
- Extension disabled by security scan after install or update.
- Extension disabled by central blocklist or policy enforcement.
- Extension update asks for new high-risk capabilities or permissions.
- Extension runtime bootstrap started, ready, degraded, and failed.
- Sandbox worker crash, timeout, protocol error, manual stop, restart, and blocked state.
- Security audit blocked an extension, including summarized critical findings.
- Extension-owned long-running processing started, completed, cancelled, and failed.
- Extension-owned service actions completed or failed, such as starting/stopping Docker-backed services.

Recommended notification behavior:

- Use `source: "extensions"` for generic extension lifecycle notifications.
- Use a more specific source only when the extension has an established module label, for example `ollama`.
- Use live activities for active downloads, installs, updates, removals, process boot, and long-running extension processing.
- Persist a final history notification when a live activity finishes, fails, or is cancelled.
- Include actionable metadata: `extension_id`, `version`, `operation`, `registry_url`, `archive_url`, `sandbox_status`, `error_code`, and `trace_id` when available.
- Deduplicate repeating sandbox/security errors with stable aggregation keys.
- Rate-limit and aggregate repeated extension failures so crash loops do not flood the Notifications center.
- Keep failure messages short in the card and store deeper diagnostics in metadata or linked details.
- Dangerous extension notifications must explain that the extension was disabled or not enabled because the security scan found blocking issues.

The migration is not complete until remote install/remove/update flows and extension processing failures are observable through the same Notifications center used by the rest of CoreUI.

### Hot Plug Runtime And Fault Isolation

Extensions must be hot-pluggable. A broken or malicious extension must not bring down the whole project.

- Installing, updating, enabling, disabling, removing, restarting, or killing an extension should affect only that extension and its registered providers/tabs/actions.
- Full project reload should not be required for normal extension lifecycle actions.
- Targeted reload should rebuild the provider registry, extension tabs, extension assets, and UI payloads without restarting CoreUI or the backend process.
- Targeted reload should be initiated by the extension-management module and applied through the Extension Host contract.
- Use generation-based runtime snapshots so a new provider registry/tabs/assets generation is built before replacing the active one.
- In-flight provider calls should finish or be cancelled explicitly; a failed reload must not corrupt the active runtime generation.
- If targeted reload fails, keep the previous stable runtime active where possible and surface the failure through API diagnostics and Notifications center.
- Sandbox worker crashes, timeouts, protocol errors, and repeated failures should mark that extension as degraded/failed/blocked, not crash the host.
- Extension actions must run with timeouts and error boundaries so one slow action cannot block all extension management.
- CoreUI should show extension-level loading/error states instead of a global application failure.
- Any operation that truly requires full app restart must explain why in the API response and UI, with a specific `restart_scope` such as `extension`, `provider_registry`, `backend`, or `app`.

### Repository Metadata Fetching

Repository-backed metadata should be fetched through a controlled backend boundary, even when the source of truth is GitHub.

- Fetch README content, releases/tags, selected-ref manifest preview, and archive URLs from the extension repository.
- Cache metadata with a short TTL to avoid GitHub rate-limit pain and keep the Extensions tab responsive.
- Expose cache age and fetch errors to CoreUI.
- Use unauthenticated public GitHub APIs by default, with optional server-side token configuration for private repos or higher limits.
- Never let the browser receive a GitHub token.
- Prefer GitHub release assets that expose digests or attestations. If only auto-generated source archives are available, record that the artifact has weaker provenance.
- For manual branch/ref installs, resolve and display the commit SHA when possible.
- Treat GitHub API failure as degraded registry UX, not as app startup failure.

### Security Enforcement

Security scanning is a mandatory gate for all downloaded or updated extension payloads.

- Scan for malware indicators, secrets, dependency risk, manifest URL/path safety, backend Python risk, Docker contract violations, dynamic execution, shell launchers, download-and-execute chains, and encoded payloads.
- Scan dependency manifests when present and retain dependency inventory or SBOM metadata where available.
- Monitor installed extension versions against vulnerability sources such as CVE/NVD/OSV when dependency metadata is available.
- Prefer lockfiles and pinned dependencies; flag extension releases that require install-time dependency resolution.
- Block or warn on activation paths that require network dependency installation unless that behavior is declared and approved.
- Scan before enabling a freshly installed extension.
- Scan before activating an updated extension version.
- Scan branch/ref installs exactly like release installs.
- If a scan fails on install, do not enable the extension.
- If a scan fails on update, disable the unsafe version and either keep the previous safe version active or mark the extension disabled until the user chooses a safe version.
- Persist security findings in installed extension diagnostics.
- Notify the user that the extension is dangerous and was disabled or blocked.
- Do not let a failed security scan be bypassed from CoreUI without an explicitly designed trusted-developer override.
- A security block must be durable: restarting the app must not silently re-enable a blocked extension.
- Enforce blocklist on startup, install, update, enable, and targeted reload.

### Publisher And Policy Governance

The registry needs a small governance model before it becomes public or shared.

- Define publisher states such as `official`, `trusted`, `community`, `experimental`, and `blocked`.
- Require stronger review for `trusted` and `official` labels.
- Keep a central blocklist for extension ids, versions, refs, repository ids, and publisher identities.
- Keep blocklist fresh through a short TTL and last-known-good local cache.
- Add name-squatting and typo-squatting checks for registry submissions.
- Add a report/appeal path for users or extension authors.
- Require manual review when ownership, publisher identity, capabilities, Docker/service behavior, or data-collection declarations change.
- Treat update capability expansion as a consent event, not a silent background detail.

### Removal And Data Ownership

Removing an extension must have explicit behavior for code, runtime state, and user data.

- Removing an extension should disable it, stop its sandbox/provider process, and remove installed extension code.
- Extension-owned containers or services must be cleaned up only through host capabilities, never direct Docker calls.
- User data, model caches, logs, and extension settings should not be deleted without an explicit confirmation path.
- The UI should distinguish remove extension, disable extension, rollback version, and purge extension data.
- Extension repositories/manifests should declare owned resources and data-retention behavior.
- Removal failures should be recoverable and visible through Notifications center.

## Extension Repo Work

Each extracted extension must satisfy these rules:

- Includes a valid `chironai-extension.json`.
- Manifest `id` matches the registry entry.
- Manifest `version` matches the release tag for stable releases.
- Backend exposes `create_provider(host_context, manifest)` through the configured entrypoint.
- Extension-owned UI is self-contained and uses supported integration points (`tab_ui`, `iframe_tab`, or `ui_schema`).
- Docker access, when needed, goes only through `host_context.docker_runtime` and `DockerContainerSpec`.
- Host capabilities must be requested in the manifest and granted by policy/user consent before use.
- No direct CoreUI imports or browser-rendered UI files outside the extension integration contract.
- Includes tests or validation scripts that can run without the main app booting.
- Release artifact contains exactly the files needed by the installer.
- Release workflow should attach a zip artifact, checksum/digest, SBOM or dependency inventory when practical, and GitHub artifact attestation when available.
- Extension README should describe capabilities, data use, service/container behavior, settings/secrets, and uninstall/data-retention behavior.
- Dependency manifests should use lockfiles or pinned versions when practical.

## Migration Phases

### Phase 1: Design And Contract Lock

- [x] Define the target module boundary: extension-management module vs CoreModule extension host/runtime contracts.
- [x] Define the extension API contract for registry, repository metadata, install state, lifecycle actions, runtime status, assets, tabs, provider catalog, and notifications.
- [x] Document registry fields and required manifest/registry invariants.
- [x] Document repository-backed README and version discovery behavior.
- [x] Document install provenance, atomic update, rollback, and blocked-extension state requirements.
- [x] Document README sanitization and capability/permission preview requirements.
- [x] Document publisher trust states, blocklist behavior, name-squatting checks, and consent on capability expansion.
- [x] Document red-team guardrails: boundary drift tests, host capability scoping, frontend token leak checks, generation-based reload, dependency controls, and notification throttling.
- [x] Decide registry URL configuration name and default behavior.
- [x] Decide whether checksum verification is required before first remote install.
- [x] Decide bundled extension policy after extraction.
- [x] Add a registry schema and validation script plan.

Phase 1 artifacts:

- `docs/EXTENSIONS_PHASE1_CONTRACT.md`
- `core/contracts/extensions_api.py`

### Phase 2: Registry Client Hardening

- [x] Move extension discovery/registry polling/status ownership out of core wiring into the extension-management module.
- [x] Replace direct core/API checks of `extensions/bundled` and `llm_extensions_service` implementation state with calls through the extension API contract.
- [x] Add tests for remote registry loading.
- [x] Add tests for bad registry shapes and missing required fields.
- [x] Add manifest id/version mismatch checks during install.
- [x] Add compatibility checks for `extension_api_version` and app version.
- [x] Add user-facing diagnostics for registry load/install failures.
- [x] Add notification events for registry load failures and remote install/download failures.
- [x] Add repository API client support for README, latest release, tags/releases list, and explicit ref archive resolution.
- [x] Add security scan enforcement for update activation and unsafe-extension disabling.
- [x] Add atomic install/update staging and previous-safe-version rollback support.
- [x] Add install-state provenance fields for repository, selected ref, resolved commit, archive URL, security scan status, and blocked reason.
- [x] Add emergency blocklist enforcement and update-capability-expansion detection.
- [x] Replace broad `restart_required` extension lifecycle responses with targeted reload status and `restart_scope`.
- [x] Add tests proving a failed extension reload does not crash the host and preserves the previous stable runtime where possible.
- [x] Add guardrail tests for boundary drift, blocklist enforcement, and direct folder/registry polling from API routes.

Phase 2 implementation notes:

- `modules/extensions_backend` now owns the registry client, GitHub repository metadata, blocklist policy, and HTTP-facing extension-management facade.
- Flask routes read extension state through `api.http.extensions_service_access`; legacy app keys are kept only as compatibility aliases behind the accessor.
- Registry loading now produces structured diagnostics instead of silently discarding bad registry entries.
- Installs now stage payloads before activation, validate manifest id/version/compatibility, preserve the previous installed payload on failed scans, and record provenance/security state.
- Unsafe installed extensions are disabled during runtime bootstrap and surfaced as blocked in installed-extension status.

### Phase 3: GitHub Registry Repository

- [x] Create the `ChironAI Extensions Registry` repository.
- [x] Add `extensions.json`.
- [x] Add JSON schema or equivalent validator.
- [x] Add CI that validates registry entries.
- [x] Add CI checks for allowed repository domains/orgs, publisher identity, repository identity, duplicate/confusing names, and required metadata.
- [x] Add registry CI checks for suspicious branch/ref defaults, weak provenance metadata, and capability expansion review flags.
- [x] Add contribution and review policy.
- [x] Publish repository entries for the first three extensions.

Phase 3 artifacts:

- Repository: `https://github.com/Rayllienstery/ChironAI-Extensions-Registry`
- GitHub repository slug: `ChironAI-Extensions-Registry`
- Initial branch: `main`
- Registry entry point: `extensions.json`
- Validator: `scripts/validate_registry.py`
- Schema: `schemas/registry.schema.json`
- CI: `.github/workflows/validate.yml`

Phase 3 implementation notes:

- The registry stores discovery metadata only. It intentionally does not store `latest_version`, `default_ref`, `archive_url`, or `source_path`.
- The initial registry points to the planned per-extension repositories for `ollama-provider`, `open-webui`, and `codex-launcher`.
- Registry CI validates required metadata, allowed GitHub owner/domain, publisher trust state, duplicate repositories, duplicate/confusing names, compatibility, high-risk consent flags, and the absence of central version/ref/archive fields.
- The validation workflow uses `actions/checkout@v6` and `actions/setup-python@v6` to avoid the GitHub Actions Node.js 20 deprecation path.

### Phase 4: Extension Repository Extraction

- [x] Extract `ollama-provider` to its own repository.
- [x] Extract `open-webui` to its own repository.
- [x] Extract `codex-launcher` to its own repository.
- [x] Add per-extension CI.
- [x] Add per-extension release tags.
- [x] Publish release archives.
- [x] Publish release digests and artifact attestations where possible.
- [x] Publish dependency inventory or SBOM where practical.
- [x] Add lockfiles or pinned dependencies where practical.
- [x] Update registry entries to repository URLs and verify release archive resolution.

Phase 4 artifacts:

- `ollama-provider`: `https://github.com/Rayllienstery/chironai-extension-ollama-provider`
  - Release: `https://github.com/Rayllienstery/chironai-extension-ollama-provider/releases/tag/v0.1.6`
  - Repository identity: `R_kgDOSqCesg`
  - Release asset digest: `sha256:aefa7a51bd85d0504a4d90e171827deddbce881822714a295221dec8e57d86c9`
- `open-webui`: `https://github.com/Rayllienstery/chironai-extension-open-webui`
  - Release: `https://github.com/Rayllienstery/chironai-extension-open-webui/releases/tag/v0.1.2`
  - Repository identity: `R_kgDOSqCfVQ`
  - Release asset digest: `sha256:5394699faa1bd95ed7360d971924e088a96c7cda9af33052e38dc32a9d27fdde`
- `codex-launcher`: `https://github.com/Rayllienstery/chironai-extension-codex-launcher`
  - Release: `https://github.com/Rayllienstery/chironai-extension-codex-launcher/releases/tag/v0.1.0`
  - Repository identity: `R_kgDOSqCgMQ`
  - Release asset digest: `sha256:374cbd3fd678f1156f9b45e55f19225cb0e120200ca08f95cf7354c16da8d8fa`

Phase 4 implementation notes:

- The extracted repositories include `chironai-extension.json`, backend code, icons, README, CHANGELOG, LICENSE, dependency inventory, validation script, and GitHub Actions CI.
- Release archives and `.sha256` files are attached to each GitHub release. GitHub also reports the uploaded zip asset digest.
- Release archives are built by per-extension GitHub Actions release workflows and have provenance attestations generated with `actions/attest@v4`; local verification with `gh attestation verify` passed for all three release zips.
- No standalone lockfiles were added because these extensions do not vendor dependencies; runtime dependencies are provided by the ChironAI host environment.
- Bundled copies remain in this repository as bootstrap/local fallback copies until Phase 6 cleanup. They should be treated as sync targets, not the long-term source of truth.

### Phase 5: App Integration

- [x] Add app configuration for registry URL.
- [x] Point a development config to the GitHub registry.
- [x] Keep local registry fallback for tests/development.
- [x] Verify CoreUI/WebUIBackend/LlmProxy consume extension state through contracts, not direct extension-manager implementation state.
- [x] Verify API routes do not directly poll registry, GitHub repositories, or local extension folders for availability.
- [x] Verify extension details modal opens from not-installed registry cards and renders GitHub README content.
- [x] Verify details header shows icon, title, selected version, status, and primary Install action.
- [x] Verify README sanitization blocks unsafe HTML, script URLs, unsafe image sources, and layout-breaking content.
- [x] Verify capability/permission badges are visible before install.
- [x] Verify publisher trust, repository identity, digest/attestation state, and branch/ref risk are visible before install.
- [x] Verify updates that add high-risk capabilities require explicit user confirmation.
- [x] Verify provenance level is visible and weak-provenance installs are warned or blocked by policy.
- [x] Verify latest release default, version dropdown, and manual branch/ref install path.
- [x] Verify CoreUI registry, install, enable, disable, remove, and sandbox actions.
- [x] Verify install, enable, disable, remove, restart, and kill are exposed as targeted extension lifecycle actions without full project reload in normal cases.
- [x] Verify a crashing extension is isolated to that extension and does not break the rest of CoreUI/backend.
- [x] Verify repeated crash/security events are aggregated and rate-limited in Notifications center.
- [x] Verify Notifications center entries for install, remove, enable, disable, restart, kill, sandbox, and security flows.
- [x] Verify Notifications center entries for registry, download/install, update, runtime action, and extension processing flows.
- [x] Verify unsafe install/update payloads are blocked or disabled with Notifications center alerts.
- [x] Verify blocklisted extension ids/versions/refs are disabled or hidden with Notifications center alerts.
- [x] Verify blocklist enforcement works from local cache during offline startup.
- [x] Verify atomic update failure keeps the previous safe version active or leaves the extension durably disabled.
- [x] Verify offline startup behavior with no network.
- [x] Update docs and changelog.

Phase 5 implementation notes:

- `config/server.yaml` now points development to the GitHub-hosted registry, with `extensions/registry/extensions.json` as local fallback.
- Environment overrides are `CHIRONAI_EXTENSIONS_REGISTRY_URL`, `CHIRONAI_EXTENSIONS_LOCAL_REGISTRY_FALLBACK`, `CHIRONAI_EXTENSIONS_BLOCKLIST_URL`, and `CHIRONAI_EXTENSIONS_LOCAL_BLOCKLIST_FALLBACK`.
- Registry loading falls back locally when the configured GitHub registry is unavailable, while preserving diagnostics for the UI/API.
- CoreUI registry cards for not-installed extensions open a details modal backed by repository README/release metadata.
- The details header includes icon/title, version dropdown, manual ref input, provenance/digest/repository metadata, capability badges, and an install action.
- Remote installs can resolve the latest GitHub release and install its release zip asset while recording provenance and security scan state.
- Manual branch/ref installs support GitHub branch names with path separators by separating the selected ref from the safe on-disk install folder name.
- Extension lifecycle actions now persist Notifications center entries for install, remove, enable, disable, sandbox restart, and sandbox kill; existing security/sandbox bridge aggregates blocked/crashing extension notifications.
- Emergency blocklist enforcement blocks install/enable, disables installed extensions during bootstrap, marks registry/installed rows, and works from the local offline cache.
- Phase 5 boundary tail closed for API routing: extension state now flows through the extension-management accessor/facade, and guardrails prevent direct API use of legacy Flask keys or bundled directory scans.
- Remaining future hardening after `0.5.1`: WebUI mutating-route authentication, richer download/update/processing progress notifications, frontend token-leak bundle scanning, and stricter weak-provenance policy.

### Phase 6: Cleanup

- [x] Keep duplicated extension code only as trusted bootstrap/offline copies until the remaining boundary cleanup is complete.
- [x] Mark bundled extensions as bootstrap copies with a clear sync procedure.
- [x] Remove obsolete local-only registry assumptions from migration docs.
- [x] Update architecture docs for the bootstrap-copy ownership model.

Phase 6 implementation notes:

- `extensions/bundled/README.md` defines bundled copies as trusted bootstrap mirrors of the public extension repositories, not canonical sources.
- `extensions/registry/README.md` defines the local registry as an offline fallback and explicitly separates its local fields from the public registry contract.
- `scripts/sync_bundled_extensions.py` can check or sync the runtime payload files from local extension repository clones.
- `docs/ARCHITECTURE.md`, `docs/legacy_map.md`, and related module READMEs now point new extension behavior to the dedicated repositories first, with bundled copies as temporary/offline mirrors.

### Phase 7: Security Policy Tail

- [x] Add emergency blocklist policy owned by `extensions_backend`.
- [x] Wire blocklist URL configuration and offline blocklist cache.
- [x] Block installs of blocklisted extension ids, refs, repositories, repository ids, or publishers.
- [x] Disable already installed blocklisted extensions during runtime bootstrap.
- [x] Prevent re-enabling blocklisted installed extensions.
- [x] Surface blocklist matches in registry and installed extension status.
- [x] Add remote blocklist publishing/validation to the public registry repository.
- [x] Add capability-expansion consent before updating an installed extension to a release with new high-risk capabilities.

Phase 7 implementation notes:

- `modules/extensions_backend/extensions_backend/blocklist.py` evaluates emergency blocklist rules from a local or remote JSON document.
- `extensions/registry/blocklist.json` is the offline cache and defaults to an empty blocklist; the default primary blocklist URL is the GitHub-hosted `ChironAI-Extensions-Registry/blocklist.json`.
- Blocklist matches are persisted as `chironai_blocklist` security scans with critical findings, so the existing Notifications center bridge reports dangerous extensions.
- Update-time high-risk capability expansion now requires an explicit install target consent flag before the new version can replace the installed one.
- `ChironAI-Extensions-Registry` commit `f38ae37` added the public `blocklist.json` artifact and validator coverage.

### Phase 8: Security Closure

- [x] Reject extension zip archives that exceed compressed, uncompressed, file-count, or compression-ratio limits.
- [x] Reject symlink entries in downloaded extension zip archives.
- [x] Reject symlink-backed extension asset paths before serving files.
- [x] Return sanitized public error codes/messages from extension HTTP routes while logging internal details server-side.
- [x] Remove the legacy `llm_extensions_service` Flask key and guard against its return.
- [ ] Add WebUI authentication and authorization for mutating extension routes.

Phase 8 implementation notes:

- Authentication is intentionally left out of this phase because it belongs to the shared WebUI/API security boundary, not to the Extensions module alone.
- Extension install/download hardening is enforced inside `ExtensionManager` before archive extraction or activation.
- Public extension route errors no longer echo raw exception strings, filesystem paths, tokens, or internal stack details to CoreUI clients.

## Definition Of Done

The migration is ready when all of the following are true:

- [x] Project version is bumped to `0.5.0` for the completed migration release.
- [x] ChironAI can load the extension registry from a GitHub-hosted URL.
- [x] ChironAI can still run in local/offline development mode.
- [x] Extension discovery, registry polling, install/update/remove, local install state, blocklist enforcement, and status polling are exposed through the extension-management module boundary outside API/core routes.
- [x] Core contains extension contracts/host/runtime/sandbox capability surfaces needed by the rest of the app.
- [x] CoreUI, WebUIBackend, and LlmProxy consume extension state through contracts and do not read extension-manager implementation state directly.
- [x] API/core routes do not directly scan extension directories or poll GitHub/registry for extension availability.
- [x] Stable installs resolve to GitHub release artifacts by default.
- [x] Registry entries store repository locations, while available versions are fetched from each extension repository.
- [x] Not-installed extension cards open a README-backed details modal before install.
- [x] Extension details header supports version selection, displays icon/title/status, and exposes the Install action.
- [x] README rendering is sanitized, resilient to GitHub failures, and does not expose GitHub tokens.
- [x] Users can see important capabilities and permissions before installing.
- [x] Users can see publisher trust, repository identity, license, and artifact integrity/provenance status before installing.
- [x] Users can see whether an install is attested, digest-only, tag-archive, or branch/ref weak provenance.
- [x] Capability expansion on update requires explicit confirmation.
- [x] Users can install the latest GitHub release, choose a repository version from a dropdown, or provide an explicit branch/tag/commit ref.
- [x] Each remote install validates archive safety, manifest id, manifest version, compatibility, and security audit.
- [x] Install state records provenance, selected ref, resolved commit when available, archive source, and security scan result.
- [x] Installs and updates are atomic, with rollback or durable disabled state on failure.
- [x] Normal extension lifecycle actions use targeted reloads and do not require full project reload.
- [x] Extension crashes, timeouts, and reload failures are isolated to the extension and reported without taking down the host.
- [x] Runtime reload uses generation snapshots or equivalent atomic swap semantics.
- [x] `host_context` is capability-scoped and routed through typed host capabilities for Docker/runtime-sensitive operations.
- [x] Every install and update is scanned by the Security module before activation.
- [x] Emergency blocklist disables unsafe extension ids/versions/refs across restarts.
- [x] Repeated extension failures are rate-limited and aggregated in Notifications center.
- [x] Unsafe extensions are blocked or disabled and the user receives a dangerous-extension notification.
- [x] Registry metadata and extension manifest versions are consistent.
- [x] Each extension lives in its own repository with README, manifest, backend entrypoint, assets, tests, and release workflow.
- [x] CoreUI shows registry and installed extension status without contract drift.
- [x] Failed installs produce actionable diagnostics in the API and UI.
- [x] Extension operations and processing failures produce live or persisted Notifications center entries.
- [x] Existing extension tests and security audit tests pass.
- [x] Documentation explains how to publish a new extension version.
- [x] Project version is bumped to `0.5.1` for post-migration security closure.
- [x] Zip bombs and zip symlink entries are rejected before extraction.
- [x] Extension assets cannot be served through symlink-backed paths.
- [x] Extension route errors expose stable public codes/messages instead of raw exception strings.
- [x] Legacy `llm_extensions_service` Flask app state is removed.
- [ ] Mutating extension routes require WebUI authentication/authorization.

## Recommended First Pull Requests

1. Add registry schema and install-time manifest id/version validation.
2. Introduce the extension-management module boundary and extension API contract.
3. Move registry/discovery/install/status ownership out of core wiring and behind the contract.
4. Add red-team guardrail tests for boundary drift, token leaks, direct folder scanning, and direct registry polling.
5. Add configurable registry URL with local fallback.
6. Add repository metadata loading for README, latest release, available versions, and explicit ref installs.
7. Add sanitized README rendering and capability/permission preview in the extension details surface.
8. Add publisher trust, repository identity, blocklist, and capability-expansion consent checks.
9. Add artifact provenance levels, digest/attestation verification, and weak-provenance warnings.
10. Add least-privilege host capability scoping.
11. Add atomic install/update staging, provenance recording, and previous-safe-version rollback.
12. Add generation-based targeted extension reload and fault isolation.
13. Add Security module enforcement for install/update scans and unsafe-extension disabling.
14. Add Notifications center coverage, rate limiting, and aggregation for extension lifecycle failures.
15. Create the `ChironAI Extensions Registry` repository with the current three entries and CI validation.
16. Extract `codex-launcher` first because it is smaller than the service-owning extensions.
17. Extract `open-webui` and verify Docker control remains exclusively in the DockerManager CoreModule through host capabilities.
18. Extract `ollama-provider` last because it is the canonical Ollama owner and has the broadest runtime surface.

## Open Questions

- Should the official registry be public, private, or public-read with reviewed contributions?
- Should extension release artifacts be signed, or is SHA-256 verification enough for the first migration?
- Should trusted bundled extensions remain installable without network access?
- Should remote extension installs support rollback to the previous installed version?
- Should registry entries support channels such as `stable`, `beta`, and `nightly`?
- Should CoreUI expose registry source and update availability directly in the Extensions tab?
- Should extension repositories declare their own notification event schema, or should the core extension host normalize all extension events into one app-level contract?
- Which GitHub API mode should be used for README/version discovery: unauthenticated public API, configured token, or raw GitHub URLs with graceful rate-limit handling?
- Which WebUI authentication/authorization model should protect extension install/remove/enable/disable/sandbox/action routes?
- Should manual branch/ref installs be hidden behind an advanced toggle?
- Should unsafe updates always disable the extension, or should the previous known-safe version remain active when available?
- Should extension install/update actions require explicit user confirmation when new capabilities or permissions appear compared with the installed version?
- Should extension-owned persistent data have a standard export/purge API before removal?
- Should public community extensions be allowed in the first release, or should the registry start official-only until governance and scanning are proven?
- Which rare lifecycle operations are allowed to require full app restart, and how should the UI communicate that scope?
- Should the extension-management module run in-process during early migration and later as HTTP, or should it start as an HTTP module from the first implementation PR?
