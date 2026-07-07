"""Static CoreUI frontend routes for the production WebUI host."""

from __future__ import annotations

import os

from flask import Flask, make_response, request, send_from_directory

_ASSET_MIME = {
    ".js": "application/javascript",
    ".css": "text/css",
    ".svg": "image/svg+xml",
    ".json": "application/json",
    ".html": "text/html",
    ".woff2": "font/woff2",
    ".woff": "font/woff",
    ".ttf": "font/ttf",
}


def _asset_mime_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return _ASSET_MIME.get(ext, "application/octet-stream")


def register_webui_static_routes(app: Flask, *, frontend_dir: str) -> None:
    """Serve React build (or legacy HTML) under /webui and /assets."""
    react_build_dir = os.path.join(frontend_dir, "dist")
    react_build_index = os.path.join(react_build_dir, "index.html")

    @app.route("/webui")
    @app.route("/webui/")
    def webui_index():
        """Serve WebUI frontend (React build if available, otherwise old HTML)."""
        if os.path.exists(react_build_index):
            with open(react_build_index, "r", encoding="utf-8") as f:
                resp = make_response(f.read())
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                resp.headers["Pragma"] = "no-cache"
                return resp

        index_path = os.path.join(frontend_dir, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "r", encoding="utf-8") as f:
                resp = make_response(f.read())
                resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
                resp.headers["Pragma"] = "no-cache"
                return resp
        return (
            "WebUI not found. Please ensure CoreModules/CoreUI/dist/index.html exists "
            "(run npm run build in CoreModules/CoreUI).",
            404,
        )

    @app.route("/webui/<path:filename>")
    def webui_static(filename: str):
        """Serve static files from CoreUI (React build or old files)."""
        react_file_path = os.path.join(react_build_dir, filename)
        if os.path.exists(react_file_path) and os.path.isfile(react_file_path):
            resp = send_from_directory(react_build_dir, filename, max_age=0)
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            return resp

        file_path = os.path.join(frontend_dir, filename)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            resp = send_from_directory(frontend_dir, filename, max_age=0)
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            return resp
        return "File not found", 404

    @app.route("/assets/<path:filename>")
    def webui_assets(filename: str):
        """Serve Vite build assets from /assets/* with optional pre-compressed variants."""
        assets_dir = os.path.join(react_build_dir, "assets")
        asset_path = os.path.join(assets_dir, filename)
        if not os.path.isfile(asset_path):
            return "File not found", 404

        accept_enc = request.headers.get("Accept-Encoding", "")
        mime = _asset_mime_type(filename)

        for enc, ext in [("br", ".br"), ("gzip", ".gz")]:
            if enc in accept_enc:
                compressed = asset_path + ext
                if os.path.isfile(compressed):
                    resp = send_from_directory(assets_dir, filename + ext, max_age=31536000)
                    resp.headers["Content-Encoding"] = enc
                    resp.headers["Content-Type"] = mime
                    resp.headers["Vary"] = "Accept-Encoding"
                    resp.headers.pop("Content-Length", None)
                    return resp

        return send_from_directory(assets_dir, filename, max_age=31536000)


__all__ = ["register_webui_static_routes"]
