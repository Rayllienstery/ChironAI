from __future__ import annotations

import os
import sys
from typing import Any


def _ensure_root_on_path() -> None:
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)
    docker_manager = os.path.join(root, "CoreModules", "DockerManager")
    if docker_manager not in sys.path:
        sys.path.insert(0, docker_manager)


class _FakeDockerManager:
    def status(self) -> dict[str, Any]:
        return {"ok": True, "cli_available": True, "engine_ready": True}

    def containers(self) -> dict[str, Any]:
        return {"ok": True, "containers": [{"name": "qdrant", "running": True}]}

    def images(self) -> dict[str, Any]:
        return {"ok": True, "images": [{"image": "qdrant/qdrant:latest"}]}

    def events(self, *, event_types: list[str] | None = None) -> Any:
        yield {"ok": True, "Type": "container", "Action": "start", "event_types": event_types}

    def pull_image(self, image: str) -> dict[str, Any]:
        if not image:
            raise ValueError("image is required")
        return {"ok": True, "image": image}

    def check_image_update(self, image: str) -> dict[str, Any]:
        if not image:
            raise ValueError("image is required")
        return {"ok": True, "image": image, "status": "unknown"}

    def update_image(self, image: str) -> dict[str, Any]:
        if not image:
            raise ValueError("image is required")
        return {"ok": True, "image": image, "changed": False}

    def start_container(self, container: str) -> dict[str, Any]:
        if not container:
            raise ValueError("container is required")
        return {"ok": True, "container": container}

    def stop_container(self, container: str) -> dict[str, Any]:
        if not container:
            raise ValueError("container is required")
        return {"ok": True, "container": container}

    def remove_container(self, container: str, *, force: bool = False) -> dict[str, Any]:
        if not container:
            raise ValueError("container is required")
        if container == "running" and not force:
            return {"ok": False, "error": "Container is running", "details": "Stop first"}
        return {"ok": True, "container": container, "force": force}

    def remove_image(self, image: str, *, force: bool = False) -> dict[str, Any]:
        if not image:
            raise ValueError("image is required")
        return {"ok": True, "image": image, "force": force}


def test_docker_routes_list_and_status(monkeypatch: Any) -> None:
    _ensure_root_on_path()
    import api.http.webui_docker_routes as docker_routes
    from api.http.rag_routes import create_app

    monkeypatch.setattr(docker_routes, "DockerManager", _FakeDockerManager)
    app = create_app()
    client = app.test_client()

    status = client.get("/api/webui/docker/status")
    containers = client.get("/api/webui/docker/containers")
    images = client.get("/api/webui/docker/images")

    assert status.status_code == 200
    assert containers.status_code == 200
    assert images.status_code == 200
    assert (status.get_json() or {})["engine_ready"] is True
    assert (containers.get_json() or {})["containers"][0]["name"] == "qdrant"
    assert (images.get_json() or {})["images"][0]["image"] == "qdrant/qdrant:latest"


def test_docker_events_route_streams_sse(monkeypatch: Any) -> None:
    _ensure_root_on_path()
    import api.http.webui_docker_routes as docker_routes
    from api.http.rag_routes import create_app

    monkeypatch.setattr(docker_routes, "DockerManager", _FakeDockerManager)
    app = create_app()
    client = app.test_client()

    response = client.get("/api/webui/docker/events")
    body = response.get_data(as_text=True)

    assert response.status_code == 200
    assert response.mimetype == "text/event-stream"
    assert "event: ready" in body
    assert "event: docker" in body
    assert '"Action":"start"' in body


def test_docker_routes_validate_action_payloads(monkeypatch: Any) -> None:
    _ensure_root_on_path()
    import api.http.webui_docker_routes as docker_routes
    from api.http.rag_routes import create_app

    monkeypatch.setattr(docker_routes, "DockerManager", _FakeDockerManager)
    app = create_app()
    client = app.test_client()

    missing_image = client.post("/api/webui/docker/images/pull", json={})
    missing_container = client.post("/api/webui/docker/containers/start", json={})
    ok_pull = client.post("/api/webui/docker/images/pull", json={"image": "ollama/ollama:latest"})
    ok_start = client.post("/api/webui/docker/containers/start", json={"container": "qdrant"})

    assert missing_image.status_code == 400
    assert missing_container.status_code == 400
    assert (missing_image.get_json() or {})["ok"] is False
    assert ok_pull.status_code == 200
    assert ok_start.status_code == 200


def test_docker_routes_destructive_delete_force(monkeypatch: Any) -> None:
    _ensure_root_on_path()
    import api.http.webui_docker_routes as docker_routes
    from api.http.rag_routes import create_app

    monkeypatch.setattr(docker_routes, "DockerManager", _FakeDockerManager)
    app = create_app()
    client = app.test_client()

    missing_confirm = client.delete("/api/webui/docker/containers", json={"container": "qdrant"})
    wrong_confirm = client.delete("/api/webui/docker/images", json={"image": "qdrant/qdrant:latest", "confirm": "qdrant"})
    blocked = client.delete("/api/webui/docker/containers", json={"container": "running", "confirm": "running"})
    forced = client.delete(
        "/api/webui/docker/containers",
        json={"container": "running", "force": True, "confirm": "running"},
    )
    image = client.delete(
        "/api/webui/docker/images",
        json={"image": "qdrant/qdrant:latest", "confirm": "qdrant/qdrant:latest"},
    )

    assert missing_confirm.status_code == 400
    assert wrong_confirm.status_code == 400
    assert (missing_confirm.get_json() or {})["code"] == "confirmation_required"
    assert (wrong_confirm.get_json() or {})["code"] == "confirmation_required"
    assert blocked.status_code == 400
    assert (blocked.get_json() or {})["error"] == "Container is running"
    assert forced.status_code == 200
    assert (forced.get_json() or {})["force"] is True
    assert image.status_code == 200
