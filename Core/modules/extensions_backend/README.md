# Extensions Backend

Target owner for ChironAI extension registry, repository metadata, install state,
security policy, blocklist enforcement, and lifecycle status.

During the migration, `CoreModules/LlmInteractor` still carries the runtime
manager used by the Flask app. New registry/GitHub ownership should move here
and expose only contract-shaped DTOs from `core/contracts/extensions_api.py` to
CoreUI, WebUIBackend, and LlmProxy.

