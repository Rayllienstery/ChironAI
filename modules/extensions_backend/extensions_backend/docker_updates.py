"""Docker container update helpers for extension-owned services."""

from __future__ import annotations

from typing import Any

EXTENSION_LABEL = "chironai.extension"

# Extensions that require a persistent volume before container recreation is allowed.
_PERSISTENT_VOLUME_REQUIRED: dict[str, str] = {
    "ollama-provider": "/root/.ollama",
    "open-webui": "/app/backend/data",
}


def list_extension_docker_bindings(docker: Any) -> dict[str, dict[str, Any]]:
    """Map installed extension ids to managed Docker containers (by label)."""
    result = docker.containers()
    if not bool(result.get("ok")):
        return {}

    bindings: dict[str, dict[str, Any]] = {}
    for row in result.get("containers") or []:
        name = str(row.get("name") or "").strip().lstrip("/")
        if not name:
            continue
        state = docker.inspect_container(name)
        if not state.exists:
            continue
        ext_id = str(state.labels.get(EXTENSION_LABEL) or "").strip()
        if not ext_id:
            continue
        volumes = [str(item).strip() for item in (state.volumes or []) if str(item).strip()]
        bindings[ext_id] = {
            "container_name": state.name,
            "image": state.image or str(row.get("image") or "").strip(),
            "running": bool(state.running),
            "volumes": volumes,
            "data_persisted": bool(volumes),
        }
    return bindings


def docker_status_for_extension(docker: Any, binding: dict[str, Any]) -> dict[str, Any]:
    image = str(binding.get("image") or "").strip()
    if not image:
        return {
            **binding,
            "update_status": "unknown",
            "update_available": False,
            "update_message": "Container image is unknown",
        }
    check = docker.check_image_update(image)
    status = str(check.get("status") or "unknown")
    return {
        **binding,
        "update_status": status,
        "update_available": status == "update_available",
        "update_message": str(check.get("message") or ""),
        "remote_digest": check.get("remote_digest"),
        "current_version": str(check.get("current_version") or "").strip(),
        "update_version": str(check.get("update_version") or "").strip(),
    }


def _volume_covers_mount(volumes: list[str], mount_path: str) -> bool:
    needle = str(mount_path or "").strip()
    if not needle:
        return False
    for item in volumes:
        parts = str(item).split(":", 2)
        if len(parts) >= 2 and parts[-1].rstrip("/") == needle.rstrip("/"):
            return True
    return False


def _ports_from_state_ports(ports: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for key, bindings in (ports or {}).items():
        container_port = str(key).split("/", 1)[0].strip()
        if not container_port:
            continue
        if not isinstance(bindings, list):
            continue
        for item in bindings:
            if not isinstance(item, dict):
                continue
            host_port = str(item.get("HostPort") or "").strip()
            if host_port:
                out.append(f"{host_port}:{container_port}")
    return out


def _container_spec_from_state(state: Any, *, image: str) -> Any:
    from docker_manager import DockerContainerSpec

    labels = dict(getattr(state, "labels", None) or {})
    return DockerContainerSpec(
        name=str(getattr(state, "name", "") or "").strip(),
        image=str(image or "").strip(),
        ports=_ports_from_state_ports(getattr(state, "ports", None) or {}),
        env={str(k): str(v) for k, v in dict(getattr(state, "env", None) or {}).items()},
        volumes=[str(item).strip() for item in (getattr(state, "volumes", None) or []) if str(item).strip()],
        restart="unless-stopped",
        labels=labels,
    )


def _wait_for_extension_health(extension_id: str, docker: Any, spec: Any) -> dict[str, Any] | None:
    if extension_id == "ollama-provider":
        host_port = "11434"
        for mapping in spec.ports or []:
            host = str(mapping).split(":", 1)[0].strip()
            if host:
                host_port = host
                break
        return docker.wait_http(f"http://127.0.0.1:{host_port}", path="/api/tags", timeout=90.0, interval=1.0)
    return None


def _persistent_volume_guard(extension_id: str, binding: dict[str, Any]) -> dict[str, Any] | None:
    """Block recreation when extension data would live only inside the container layer."""
    required_mount = _PERSISTENT_VOLUME_REQUIRED.get(extension_id)
    if not required_mount:
        return None
    volumes = [str(item).strip() for item in (binding.get("volumes") or []) if str(item).strip()]
    if _volume_covers_mount(volumes, required_mount):
        return None
    return {
        "ok": False,
        "error": (
            f"Refusing to recreate {extension_id!r}: no persistent Docker volume is mounted at "
            f"{required_mount}. Container removal would risk losing local data."
        ),
        "extension_id": extension_id,
        "required_mount": required_mount,
        "volumes": volumes,
    }


def enrich_installed_with_docker(
    installed: list[dict[str, Any]],
    docker: Any | None,
    *,
    include_version_check: bool = True,
) -> list[dict[str, Any]]:
    if docker is None or not installed:
        return installed
    bindings = list_extension_docker_bindings(docker)
    out: list[dict[str, Any]] = []
    for item in installed:
        ext_id = str(item.get("id") or "")
        binding = bindings.get(ext_id)
        docker_info = (
            docker_status_for_extension(docker, binding)
            if binding and include_version_check
            else {**binding, "update_status": "not_checked", "update_available": False}
            if binding
            else None
        )
        out.append({**item, "docker": docker_info})
    return out


def update_extension_docker_container(
    extension_id: str,
    *,
    docker: Any,
    manager: Any,
    runtime: Any | None,
    skip_image_pull: bool = False,
) -> dict[str, Any]:
    ext_id = str(extension_id or "").strip()
    if not ext_id:
        return {"ok": False, "error": "extension_id is required"}

    bindings = list_extension_docker_bindings(docker)
    binding = bindings.get(ext_id)
    if not binding:
        return {"ok": False, "error": f"Extension {ext_id!r} has no Docker container", "extension_id": ext_id}

    image = str(binding.get("image") or "").strip()
    container_name = str(binding.get("container_name") or "").strip()
    volumes = [str(item).strip() for item in (binding.get("volumes") or []) if str(item).strip()]
    if not image:
        return {"ok": False, "error": "Container image is unknown", "extension_id": ext_id}

    guard = _persistent_volume_guard(ext_id, binding)
    if guard is not None:
        return guard

    state = docker.inspect_container(container_name) if container_name else None
    if state is None or not state.exists:
        return {"ok": False, "error": f"Extension {ext_id!r} has no Docker container", "extension_id": ext_id}
    spec = _container_spec_from_state(state, image=image)

    pulled: dict[str, Any] = {"ok": True, "image": image, "changed": False, "skipped": True}
    if not skip_image_pull:
        pulled = docker.update_image(image)
        if not bool(pulled.get("ok")):
            return {**pulled, "extension_id": ext_id, "image": image}

    if container_name and docker.container_exists(container_name):
        if docker.container_running(container_name):
            stopped = docker.stop_container(container_name)
            if not bool(stopped.get("ok")):
                return {**stopped, "extension_id": ext_id, "image": image, "volumes_preserved": volumes}
        # docker rm without -v keeps named/bind volumes on the host.
        removed = docker.remove_container(container_name, force=True)
        if not bool(removed.get("ok")):
            return {**removed, "extension_id": ext_id, "image": image, "volumes_preserved": volumes}

    ensured = docker.ensure_container(spec)
    if not bool(ensured.get("ok")):
        return {
            **ensured,
            "extension_id": ext_id,
            "image": image,
            "container_name": container_name,
            "image_update": pulled,
            "volumes_preserved": volumes,
        }

    health = _wait_for_extension_health(ext_id, docker, spec)
    if health is not None and not bool(health.get("ok")):
        return {
            "ok": False,
            "extension_id": ext_id,
            "image": image,
            "container_name": container_name,
            "message": f"Container recreated but health check failed: {health.get('error') or 'timeout'}",
            "image_update": pulled,
            "recreate": ensured,
            "health": health,
            "volumes_preserved": volumes,
        }

    _ = manager  # reserved for future extension-specific hooks
    _ = runtime
    ok = True
    action = str(ensured.get("action") or "recreated")
    preserved_note = (
        f" Persistent Docker volume(s) preserved: {', '.join(volumes)}."
        if volumes
        else ""
    )
    changed = bool(pulled.get("changed"))
    base_message = (
        f"Container {action} with image {image}."
        if changed
        else f"Image already up to date; container {action}."
    )
    return {
        "ok": ok,
        "extension_id": ext_id,
        "image": image,
        "container_name": container_name,
        "message": f"{base_message}{preserved_note}".strip(),
        "image_update": pulled,
        "recreate": ensured,
        "health": health,
        "recreated": ok,
        "volumes_preserved": volumes,
        "data_persisted": bool(volumes),
    }


def update_extension_docker_containers(
    extension_ids: list[str],
    *,
    docker: Any,
    manager: Any,
    runtime: Any | None,
    skip_image_pull: bool = False,
) -> dict[str, Any]:
    ids = [str(item or "").strip() for item in extension_ids if str(item or "").strip()]
    if not ids:
        return {"ok": False, "error": "extension_ids is required"}

    results: list[dict[str, Any]] = []
    for ext_id in ids:
        results.append(
            update_extension_docker_container(
                ext_id,
                docker=docker,
                manager=manager,
                runtime=runtime,
                skip_image_pull=skip_image_pull,
            )
        )

    failed = [item for item in results if not bool(item.get("ok"))]
    return {
        "ok": not failed,
        "results": results,
        "updated": [item for item in results if bool(item.get("ok"))],
        "failed": failed,
        "message": (
            f"Updated {len(results) - len(failed)} of {len(results)} extension container(s)."
            if not failed
            else f"{len(failed)} of {len(results)} extension container update(s) failed."
        ),
    }
