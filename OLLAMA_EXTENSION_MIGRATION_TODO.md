# Ollama Extension Migration TODO

This is the decision-complete migration guide for keeping Ollama behavior owned
by the `ollama-provider` extension while keeping ChironAI's core proxy
provider-generic.

## Ownership

- `ollama-provider` owns Ollama behavior, model discovery, pull/status actions,
  embedding, rerank, raw generation, and raw chat operations.
- Keep public `/v1/chat/completions`, `/v1/messages`, and `/v1/responses`
  compatibility in the core proxy.
- Do not make CoreUI know Ollama internals; CoreUI must use provider catalog,
  provider actions, or WebUI API contracts.
- Extension-owned Docker work must go through `host_context.docker_runtime`.
- Extension containers must be described with `DockerContainerSpec`.
- Do not move Qdrant into the Ollama extension. Qdrant remains RAG service
  infrastructure/runtime ownership.

## Compatibility Rules

- Do not add new core direct-Ollama HTTP ownership.
- Keep raw Ollama-compatible `/api/tags`, `/api/show`, `/api/generate`, and
  `/api/chat` behavior inside `ollama-provider`.
- Keep legacy completion/generate behavior inside provider-owned surfaces, not
  the core `/v1` proxy.
- Fail clearly when provider runtime is unavailable; do not fall back to direct
  `localhost:11434` calls from core code.

## Manual Smoke Checklist

- Start the app and confirm provider catalog contains Ollama models.
- Pull an Ollama model through the extension action path.
- Confirm `/v1/models` includes configured proxy builds.
- Confirm raw Ollama-compatible routes are not registered by the main app.
- Confirm `/v1/chat/completions`, `/v1/messages`, and `/v1/responses` still work.
- Confirm RAG embedding still works without CoreUI calling Ollama directly.

## Suggested Regression Searches

- `from infrastructure.ollama`
- `llm_extensions_service`
- `llm_interactor_runtime`
- `llm_provider_registry`
- `docker `
- `/api/tags`
- `/v1/completions`
- `raw_ollama`

## Acceptance Criteria

- New runtime Ollama behavior is implemented in the extension first.
- Core API routes use provider/runtime contracts rather than extension internals.
- Core no longer exposes raw Ollama-compatible routes.
- CoreUI remains provider-agnostic.
- Docker ownership remains behind host capabilities.
