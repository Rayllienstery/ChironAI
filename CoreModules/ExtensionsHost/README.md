# ExtensionsHost

Host-side extension runtime bridge for ChironAI.

## Ownership

| Concern | Owner |
|---------|-------|
| Registry polling, GitHub metadata, install/update, blocklist | `Core/modules/extensions_backend` |
| Host wiring, provider runtime bootstrap, capability bridge | **ExtensionsHost** (`extensions_host`) |
| Out-of-process worker isolation | `CoreModules/ExtensionsSandbox` |
| Shared DTOs and HTTP constants | `core/contracts/extensions_api.py` |

`extensions_host` is the only CoreModule that may compose `extensions_backend`
with `llm_interactor` for host startup. Application routes and other CoreModules
must consume extension state through contracts (`extensions_service_access`) or
`build_extension_host_stack()`.

## Usage

```python
from extensions_host import ExtensionHostStack, build_extension_host_stack

stack = build_extension_host_stack(
    project_root="/path/to/repo",
    settings_repo=settings_repo,
    chat_client=chat_client,
    get_settings_repository=get_settings_repository,
)
if stack is not None:
    stack.service.start_background_bootstrap()
```
