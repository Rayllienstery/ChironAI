# ADR 0005: Docker Contract for Extensions and Host Service Control

## Status

Accepted

## Context

Multiple subsystems need to run containers: the Ollama extension, Open WebUI extension, Qdrant for RAG, and internal test fixtures. Early code resolved Docker CLI paths, shelled out to `docker`, or called Docker SDK directly from extension backends. This created security holes, platform-specific bugs, and unclear ownership over container lifecycle.

## Decision

We centralize Docker runtime ownership and expose it through a host contract:

1. **Host contract:** `host_context.docker_runtime` is the only sanctioned way for extensions and host services to manage containers.
2. **Container spec:** All container declarations use `DockerContainerSpec` (image, ports, volumes, environment, healthcheck, resource limits).
3. **Extension prohibition:** Extensions must not:
   - Call Docker CLI or Docker SDK directly.
   - Shell out to Docker commands.
   - Resolve Docker binary paths.
   - Call CoreUI routes such as `/api/webui/docker/*`.
4. **Service control split:**
   - Qdrant-related WebUI actions delegate to `RagRuntime` (`CoreModules/RagService/rag_service/runtime.py`).
   - Extension-owned services use DockerManager host capabilities.
   - `Core/api/http/service_control.py` is the lifecycle bridge; it does not mix Qdrant logic with extension logic.
5. **Audit:** `tests/llm_interactor/test_extension_docker_contract_audit.py` and related tests reject direct Docker access in bundled extension backends.

## Consequences

- **Positive:**
  - Container lifecycle is consistent across extensions.
  - Security audit can mechanically detect Docker policy violations.
  - Platform differences (Windows vs. Linux paths, WSL, etc.) are handled in one place.
- **Negative:**
  - Extensions that previously relied on direct Docker calls had to be refactored.
  - The host runtime must be available for any extension that needs containers.
- **Neutral:**
  - `docker-compose.yml` declares Qdrant, app, and Ollama services with healthchecks for local development.

## References

- `AI_RULES.md` sections 4 and 7 (high-risk area 5)
- `CoreModules/DockerManager/`
- `Core/api/http/service_control.py`
- `CoreModules/RagService/rag_service/runtime.py`
- `tests/llm_interactor/test_extension_docker_contract_audit.py`
- `tests/llm_interactor/test_extension_docker_policy.py`
