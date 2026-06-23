# ExtensionsSandbox

ExtensionsSandbox runs extension providers in a separate worker process.
It limits direct host access by forwarding only supported host capability calls.

## Purpose

- Start extension provider factories outside the main backend process.
- Proxy provider methods such as `describe`, `list_models`, `invoke`, and UI actions.
- Forward approved host calls for settings, chat client, metadata, and Docker runtime.
- Preserve extension failure diagnostics without crashing the main application.

## Setup

- Install with `pip install -e CoreModules/ExtensionsSandbox`.
- The worker also needs `Core/` and the relevant extension source directory on the Python path.
- LlmInteractor starts the sandbox automatically during extension discovery.
- Do not start the worker manually except while debugging the protocol.

## Entrypoints

- `extensions_sandbox.start_sandboxed_extension_provider` creates a provider proxy.
- `extensions_sandbox.worker` is the worker process entrypoint.
- `extensions_sandbox.client.ExtensionWorkerClient` owns the host-side RPC process.
- `extensions_sandbox.provider.SandboxedExtensionProvider` exposes the LLMProvider-like facade.

## Protocol

- Host and worker communicate with JSON messages over stdin/stdout.
- Extension stdout is redirected away from the protocol stream.
- Host calls are time-limited by target and method.
- Worker responses are serialized through `extensions_sandbox.serialization`.

## Testing

- Run `pytest -q tests/extensions_sandbox`.
- Run `pytest -q tests/llm_interactor` after changing provider proxy behavior.
- Cover timeout, Unicode, Docker proxy, and worker shutdown paths.
- Keep protocol changes backward-compatible with existing extension providers.

## Dependencies

- Shared LLM contracts from `Core/core/contracts/llm_runtime.py`.
- Provider loading helpers from `extensions_sandbox.loader`.
- Runtime orchestration from `llm_interactor`.
- No direct Docker CLI access is allowed from sandboxed extension code.
