"""DockerManager routes for WebUI."""

from __future__ import annotations

import json
from typing import Any

from flask import Blueprint, Response, jsonify, request, stream_with_context

from docker_manager import DockerManager


def _error_payload(error: str, details: str = "") -> dict[str, Any]:
    return {"ok": False, "error": str(error or "Docker action failed"), "details": str(details or "")}


def _status_for_result(result: dict[str, Any]) -> int:
    return 200 if bool(result.get("ok")) else 400


def _body() -> dict[str, Any]:
    data = request.get_json(force=True, silent=True) or {}
    return data if isinstance(data, dict) else {}


def register_docker_routes(
    bp: Blueprint,
    *,
    error_log: Any,
    manager_factory: Any | None = None,
) -> None:
    def manager() -> DockerManager:
        if callable(manager_factory):
            return manager_factory()
        return DockerManager()

    @bp.route("/docker/status", methods=["GET"])
    def docker_status() -> Any:
        try:
            return jsonify(manager().status())
        except Exception as e:
            error_log.error("webui_docker_routes.docker_status", exc_info=True)
            return jsonify(_error_payload("Failed to read Docker status", str(e))), 500

    @bp.route("/docker/containers", methods=["GET"])
    def docker_containers() -> Any:
        try:
            result = manager().containers()
            return jsonify(result), _status_for_result(result)
        except Exception as e:
            error_log.error("webui_docker_routes.docker_containers", exc_info=True)
            return jsonify(_error_payload("Failed to list Docker containers", str(e))), 500

    @bp.route("/docker/images", methods=["GET"])
    def docker_images() -> Any:
        try:
            result = manager().images()
            return jsonify(result), _status_for_result(result)
        except Exception as e:
            error_log.error("webui_docker_routes.docker_images", exc_info=True)
            return jsonify(_error_payload("Failed to list Docker images", str(e))), 500

    @bp.route("/docker/events", methods=["GET"])
    def docker_events() -> Any:
        docker = manager()

        def _stream() -> Any:
            yield "event: ready\ndata: {}\n\n"
            try:
                for event in docker.events(event_types=["container", "image"]):
                    yield f"event: docker\ndata: {json.dumps(event, separators=(',', ':'))}\n\n"
            except GeneratorExit:
                raise
            except Exception as e:
                error_log.error("webui_docker_routes.docker_events", exc_info=True)
                yield f"event: error\ndata: {json.dumps(_error_payload('Docker event stream failed', str(e)), separators=(',', ':'))}\n\n"

        return Response(
            stream_with_context(_stream()),
            mimetype="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @bp.route("/docker/images/pull", methods=["POST"])
    def docker_pull_image() -> Any:
        try:
            image = str(_body().get("image") or "").strip()
            result = manager().pull_image(image)
            return jsonify(result), _status_for_result(result)
        except Exception as e:
            error_log.error("webui_docker_routes.docker_pull_image", exc_info=True)
            return jsonify(_error_payload(str(e))), 400

    @bp.route("/docker/images/check-update", methods=["POST"])
    def docker_check_image_update() -> Any:
        try:
            image = str(_body().get("image") or "").strip()
            result = manager().check_image_update(image)
            return jsonify(result), _status_for_result(result)
        except Exception as e:
            error_log.error("webui_docker_routes.docker_check_image_update", exc_info=True)
            return jsonify(_error_payload(str(e))), 400

    @bp.route("/docker/images/update", methods=["POST"])
    def docker_update_image() -> Any:
        try:
            image = str(_body().get("image") or "").strip()
            result = manager().update_image(image)
            return jsonify(result), _status_for_result(result)
        except Exception as e:
            error_log.error("webui_docker_routes.docker_update_image", exc_info=True)
            return jsonify(_error_payload(str(e))), 400

    @bp.route("/docker/containers/start", methods=["POST"])
    def docker_start_container() -> Any:
        try:
            container = str(_body().get("container") or "").strip()
            result = manager().start_container(container)
            return jsonify(result), _status_for_result(result)
        except Exception as e:
            error_log.error("webui_docker_routes.docker_start_container", exc_info=True)
            return jsonify(_error_payload(str(e))), 400

    @bp.route("/docker/containers/stop", methods=["POST"])
    def docker_stop_container() -> Any:
        try:
            container = str(_body().get("container") or "").strip()
            result = manager().stop_container(container)
            return jsonify(result), _status_for_result(result)
        except Exception as e:
            error_log.error("webui_docker_routes.docker_stop_container", exc_info=True)
            return jsonify(_error_payload(str(e))), 400

    @bp.route("/docker/containers", methods=["DELETE"])
    def docker_remove_container() -> Any:
        try:
            data = _body()
            container = str(data.get("container") or "").strip()
            force = bool(data.get("force"))
            result = manager().remove_container(container, force=force)
            return jsonify(result), _status_for_result(result)
        except Exception as e:
            error_log.error("webui_docker_routes.docker_remove_container", exc_info=True)
            return jsonify(_error_payload(str(e))), 400

    @bp.route("/docker/images", methods=["DELETE"])
    def docker_remove_image() -> Any:
        try:
            data = _body()
            image = str(data.get("image") or "").strip()
            force = bool(data.get("force"))
            result = manager().remove_image(image, force=force)
            return jsonify(result), _status_for_result(result)
        except Exception as e:
            error_log.error("webui_docker_routes.docker_remove_image", exc_info=True)
            return jsonify(_error_payload(str(e))), 400
