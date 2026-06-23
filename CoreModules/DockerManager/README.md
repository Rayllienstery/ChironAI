# DockerManager

DockerManager is the host-owned Docker runtime adapter used by ChironAI.
It wraps Docker CLI operations behind a Python interface that other modules can consume safely.

## Purpose

- Inspect Docker availability and container state.
- Start, stop, and inspect extension-owned containers through host capabilities.
- Check image update metadata where the local Docker installation supports it.
- Keep extension code away from direct Docker CLI or SDK access.

## Setup

- Install the package in editable mode when working on it: `pip install -e CoreModules/DockerManager`.
- Docker Desktop or Docker Engine must be available on the host.
- The module intentionally uses the Docker CLI rather than the Docker Python SDK.
- Commands should run from the repository root so tests can resolve the package path.

## Entrypoints

- Import `DockerManager` from `docker_manager`.
- Container specifications come from `core.contracts.docker_runtime.DockerContainerSpec`.
- Extension providers receive Docker access through `host_context.docker_runtime`.
- Public HTTP service actions are routed through the host, not through this package directly.

## Testing

- Run `pytest -q tests/docker_manager`.
- Run extension Docker contract tests when changing host capability behavior.
- Avoid tests that require a live Docker daemon unless explicitly marked as integration.
- Mock CLI calls for unit coverage of parsing and error handling.

## Dependencies

- Python standard library subprocess and JSON parsing.
- Docker CLI installed on the system path.
- Shared Docker contract DTOs from `Core/core/contracts`.
- No dependency on Docker SDK is expected or required.

## Ownership Notes

- DockerManager is a host capability boundary, not an extension implementation detail.
- Extensions declare desired containers and call host APIs.
- This module should stay small enough to audit because it can affect local services.
