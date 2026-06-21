# LlmInteractor

LlmInteractor owns provider-neutral LLM runtime orchestration for ChironAI.
It is the bridge between extension manifests, provider discovery, and runtime chat/model calls.

## Purpose

- Load extension manifests from installed and bundled extension directories.
- Start extension providers directly or through the sandbox worker.
- Register LLM providers in a runtime registry.
- Expose provider rows, model listings, health, and chat invocation helpers.
- Keep OpenAI-compatible HTTP behavior decoupled from provider implementation details.

## Setup

- Install in editable mode with `pip install -e CoreModules/LlmInteractor`.
- The repository test configuration adds this module to `PYTHONPATH`.
- Runtime callers must also have `Core/` importable for shared contracts.
- Extension loading also depends on `CoreModules/Security` and `CoreModules/ExtensionsSandbox`.

## Entrypoints

- `llm_interactor.ExtensionManager` manages installed extension state and runtime bootstrap.
- `llm_interactor.LLMRuntime` invokes registered providers.
- `llm_interactor.ProviderRegistry` owns provider lookup and duplicate protection.
- `llm_interactor.discovery.load_manifest_from_dir` validates extension manifests.
- `llm_interactor.manifest.ExtensionManifest` is the manifest DTO.

## Manifest And Security

- Manifest files are named `chironai-extension.json`.
- `manifest_sha256` is validated when present.
- Provider capabilities are checked against declared manifest capabilities.
- Installation rejects incompatible registry or manifest API versions.
- High-risk capability expansion requires explicit install consent.

## Testing

- Run `pytest -q tests/llm_interactor`.
- Run `pytest -q tests/extensions_backend` after install or registry changes.
- Run `pytest -q tests/extensions_sandbox` after sandbox protocol changes.
- Use targeted tests for manifest and capability enforcement before broader gates.

## Dependencies

- Shared contracts from `Core/core/contracts/llm_runtime.py`.
- Security audit helpers from `chironai_security`.
- Sandboxed providers from `extensions_sandbox`.
- Extension management state stored through the host settings repository.
