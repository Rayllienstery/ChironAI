"""Prompt and prompt-trash routes for the WebUI blueprint."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from flask import Blueprint, jsonify, request

from api.http.webui_prompts import (
    has_unsafe_path_segments,
    is_readme_name,
    next_trash_prompt_path,
    prompt_file_path,
    prompt_original_name,
    prompt_trash_entries,
)
from config.rag_prompts import list_rag_prompt_names


def register_prompt_routes(
    bp: Blueprint,
    *,
    prompts_dir: Path,
    trash_dir: Path,
    error_log: Any,
) -> None:
    @bp.route("/prompts", methods=["GET"])
    def get_prompts() -> Any:
        try:
            names = list_rag_prompt_names()
            return jsonify({"prompts": [{"name": name, "id": name} for name in names]})
        except Exception as e:
            error_log.error("webui_routes.get_prompts", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/prompts/<name>", methods=["GET"])
    def get_prompt_content(name: str) -> Any:
        try:
            if has_unsafe_path_segments(name):
                return jsonify({"error": "Invalid prompt name"}), 400

            path = prompt_file_path(prompts_dir, name)
            if not path.is_file():
                return jsonify({"error": "Prompt not found"}), 404

            return jsonify({"name": name, "content": path.read_text(encoding="utf-8")})
        except Exception as e:
            error_log.error("webui_routes.get_prompt_content", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/prompts", methods=["POST"])
    def create_prompt() -> Any:
        try:
            body = request.get_json(force=True, silent=True) or {}
            source_name = body.get("source_name")
            name = body.get("name")
            content = body.get("content")

            if not name:
                return jsonify({"error": "name is required"}), 400
            if has_unsafe_path_segments(name):
                return jsonify({"error": "Invalid prompt name"}), 400
            if is_readme_name(name):
                return jsonify({"error": "Cannot create a file named README"}), 403

            path = prompt_file_path(prompts_dir, name)
            if path.exists():
                return jsonify({"error": "Prompt already exists"}), 409

            if source_name and not content:
                if has_unsafe_path_segments(source_name):
                    return jsonify({"error": "Invalid source prompt name"}), 400
                source_path = prompt_file_path(prompts_dir, source_name)
                if not source_path.is_file():
                    return jsonify({"error": "Source prompt not found"}), 404
                content = source_path.read_text(encoding="utf-8")

            if not content:
                return jsonify({"error": "content is required"}), 400

            prompts_dir.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            return jsonify({"name": name, "status": "created"})
        except Exception as e:
            error_log.error("webui_routes.create_prompt", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/prompts/<name>", methods=["PUT"])
    def update_prompt(name: str) -> Any:
        try:
            if has_unsafe_path_segments(name):
                return jsonify({"error": "Invalid prompt name"}), 400

            body = request.get_json(force=True, silent=True) or {}
            new_name = body.get("new_name")
            content = body.get("content")

            path = prompt_file_path(prompts_dir, name)
            if not path.is_file():
                return jsonify({"error": "Prompt not found"}), 404
            if is_readme_name(name):
                return jsonify({"error": "README cannot be edited"}), 403

            if new_name and new_name != name:
                if has_unsafe_path_segments(new_name):
                    return jsonify({"error": "Invalid new prompt name"}), 400
                if is_readme_name(new_name):
                    return jsonify({"error": "Cannot rename to README"}), 403
                new_path = prompt_file_path(prompts_dir, new_name)
                if new_path.exists():
                    return jsonify({"error": "New prompt name already exists"}), 409
                if content is not None:
                    new_path.write_text(content, encoding="utf-8")
                    path.unlink()
                else:
                    path.rename(new_path)
                return jsonify({"name": new_name, "status": "renamed"})

            if content is not None:
                path.write_text(content, encoding="utf-8")
                return jsonify({"name": name, "status": "updated"})

            return jsonify({"error": "No changes specified"}), 400
        except Exception as e:
            error_log.error("webui_routes.update_prompt", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/prompts/<name>", methods=["DELETE"])
    def delete_prompt(name: str) -> Any:
        try:
            if has_unsafe_path_segments(name):
                return jsonify({"error": "Invalid prompt name"}), 400
            if is_readme_name(name):
                return jsonify({"error": "README cannot be deleted"}), 403

            path = prompt_file_path(prompts_dir, name)
            if not path.is_file():
                return jsonify({"error": "Prompt not found"}), 404

            trash_dir.mkdir(parents=True, exist_ok=True)
            path.rename(next_trash_prompt_path(trash_dir, name))
            return jsonify({"name": name, "status": "moved_to_trash"})
        except Exception as e:
            error_log.error("webui_routes.delete_prompt", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/prompts/trash", methods=["GET"])
    def get_trash_prompts() -> Any:
        try:
            return jsonify({"prompts": prompt_trash_entries(trash_dir)})
        except Exception as e:
            error_log.error("webui_routes.get_trash_prompts", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/prompts/trash/<trash_name>", methods=["GET"])
    def get_trash_prompt_content(trash_name: str) -> Any:
        try:
            if has_unsafe_path_segments(trash_name):
                return jsonify({"error": "Invalid trash name"}), 400

            trash_path = trash_dir / trash_name
            if not trash_path.is_file():
                return jsonify({"error": "Prompt not found in trash"}), 404

            return jsonify(
                {
                    "name": prompt_original_name(trash_path),
                    "trash_name": trash_name,
                    "content": trash_path.read_text(encoding="utf-8"),
                }
            )
        except Exception as e:
            error_log.error("webui_routes.get_trash_prompt_content", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/prompts/trash/<trash_name>", methods=["PUT"])
    def update_trash_prompt(trash_name: str) -> Any:
        try:
            if has_unsafe_path_segments(trash_name):
                return jsonify({"error": "Invalid trash name"}), 400

            body = request.get_json(force=True, silent=True) or {}
            content = body.get("content")
            if content is None:
                return jsonify({"error": "content is required"}), 400

            trash_path = trash_dir / trash_name
            if not trash_path.is_file():
                return jsonify({"error": "Prompt not found in trash"}), 404

            trash_path.write_text(content, encoding="utf-8")
            return jsonify(
                {
                    "name": prompt_original_name(trash_path),
                    "trash_name": trash_name,
                    "status": "updated",
                }
            )
        except Exception as e:
            error_log.error("webui_routes.update_trash_prompt", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/prompts/trash/<trash_name>/restore", methods=["POST"])
    def restore_prompt(trash_name: str) -> Any:
        try:
            if has_unsafe_path_segments(trash_name):
                return jsonify({"error": "Invalid trash name"}), 400

            trash_path = trash_dir / trash_name
            if not trash_path.is_file():
                return jsonify({"error": "Prompt not found in trash"}), 404

            name = prompt_original_name(trash_path)
            restore_path = prompt_file_path(prompts_dir, name)
            if restore_path.exists():
                return jsonify({"error": "A prompt with this name already exists"}), 409

            trash_path.rename(restore_path)
            return jsonify({"name": name, "status": "restored"})
        except Exception as e:
            error_log.error("webui_routes.restore_prompt", exc_info=True)
            return jsonify({"error": str(e)}), 500

    @bp.route("/prompts/trash", methods=["DELETE"])
    def clear_trash() -> Any:
        try:
            if not trash_dir.is_dir():
                return jsonify({"status": "cleared", "deleted_count": 0})

            deleted_count = 0
            for path in trash_dir.iterdir():
                if path.suffix.lower() == ".md" and not path.name.startswith("."):
                    path.unlink()
                    deleted_count += 1
            return jsonify({"status": "cleared", "deleted_count": deleted_count})
        except Exception as e:
            error_log.error("webui_routes.clear_trash", exc_info=True)
            return jsonify({"error": str(e)}), 500


__all__ = ["register_prompt_routes"]
