# Ollama Extension Migration TODO

This is the decision-complete migration guide for keeping Ollama behavior owned
by the `ollama-provider` extension while preserving the public compatibility
surface exposed by ChironAI.

## Ownership

- `ollama-provider` owns Ollama behavior, model discovery, pull/status actions,
  embedding, rerank, raw generation, and raw chat operations.
- Preserve public HTTP compatibility for existing clients throughout migration.
- Do not make CoreUI know Ollama internals; CoreUI must use provider catalog,
  provider actions, or WebUI API contracts.
- Extension-owned Docker work must go through `host_context.docker_runtime`.
- Extension containers must be described with `DockerContainerSpec`.
- Do not move Qdrant into the Ollama extension. Qdrant remains RAG service
  infrastructure/runtime ownership.

## Compatibility Rules

- Do not remove old env/config names until a documented migration path exists.
- Preserve `GET /api/tags` compatibility for Ollama-style clients.
- Preserve `/api/show`, `/api/generate`, `/api/chat`, and `/v1/completions`
  compatibility unless a release explicitly deprecates them.
- Keep direct upstream fallbacks only as documented compatibility paths while
  the extension runtime is unavailable or still loading.

## Manual Smoke Checklist

- Start the app and confirm provider catalog contains Ollama models.
- Pull an Ollama model through the extension action path.
- Confirm `/v1/models` includes configured proxy builds.
- Confirm `GET /api/tags` returns an Ollama-compatible response.
- Confirm `/v1/completions` still works for legacy edit-prediction clients.
- Confirm RAG embedding still works without CoreUI calling Ollama directly.

## Suggested Regression Searches

- `from infrastructure.ollama`
- `llm_extensions_service`
- `llm_interactor_runtime`
- `llm_provider_registry`
- `docker `
- `/api/tags`
- `raw_ollama`

## Acceptance Criteria

- New runtime Ollama behavior is implemented in the extension first.
- Core API routes use provider/runtime contracts rather than extension internals.
- Public HTTP compatibility endpoints remain tested.
- CoreUI remains provider-agnostic.
- Docker ownership remains behind host capabilities.
