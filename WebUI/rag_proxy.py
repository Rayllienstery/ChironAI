"""
OpenAI-compatible RAG proxy for Zed (and other clients).
Accepts POST /v1/chat/completions, runs RAG (embed -> Qdrant), calls Ollama /api/chat,
returns OpenAI-format response. Listen on 0.0.0.0:8080 for remote access (e.g. Zed on Mac).

Usage:
  On PC: python rag_proxy.py  (after starting Ollama and Qdrant)
  On Mac Zed: OpenAI API Compatible -> API URL: http://<PC_IP>:8080, model: ChironAI-Worker
  Windows firewall: allow inbound on port 8080.

Uses api.http.rag_routes.create_app; prompt and model come from config via application.rag.params.
"""

import logging
import os
import sys
import threading

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)
_PROXY_V2_SRC = os.path.join(_ROOT_DIR, "CoreModules", "ProxyV2")
if _PROXY_V2_SRC not in sys.path:
    sys.path.insert(0, _PROXY_V2_SRC)

from flask import send_from_directory

from config import get_log_level, get_pass_proxy_v2_port, get_server_host, get_server_port
from api.http.rag_routes import create_app

logging.basicConfig(
    level=get_log_level(),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
# Frontend moved to modules/webui_frontend
WEBUI_FRONTEND_DIR = os.path.join(PROJECT_ROOT, "modules", "webui_frontend")

# create_app() registers webui_bp, so /api/webui/* (open-webui/status, start, stop, etc.) is available
app = create_app(webui_dir=BASE_DIR)


def _start_pass_proxy_v2(main_app) -> None:
    """Ollama passthrough on pass_proxy_v2_port (default 8081); same process as rag_proxy."""
    try:
        from werkzeug.serving import make_server

        from api.http.proxy_v2_wiring import build_proxy_v2_wiring
        from proxy_v2 import create_pass_proxy_v2_app

        wiring = build_proxy_v2_wiring(main_app)
        v2_app = create_pass_proxy_v2_app(wiring)
        host = get_server_host()
        port = get_pass_proxy_v2_port()
        srv = make_server(host, port, v2_app, threaded=True)
        threading.Thread(target=srv.serve_forever, name="proxy_v2", daemon=True).start()
        logging.getLogger(__name__).info("Proxy V2 listening on %s:%s", host, port)
    except Exception:
        logging.getLogger(__name__).exception("Failed to start Proxy V2; continuing without 8081")


threading.Thread(target=_start_pass_proxy_v2, args=(app,), name="proxy_v2_boot", daemon=True).start()

# Serve static files from webui_frontend
# Check if React build exists, otherwise fall back to old HTML
REACT_BUILD_DIR = os.path.join(WEBUI_FRONTEND_DIR, "dist")
REACT_BUILD_INDEX = os.path.join(REACT_BUILD_DIR, "index.html")

@app.route("/webui")
@app.route("/webui/")
def webui_index():
    """Serve WebUI frontend (React build if available, otherwise old HTML)."""
    # Try React build first
    if os.path.exists(REACT_BUILD_INDEX):
        with open(REACT_BUILD_INDEX, "r", encoding="utf-8") as f:
            return f.read()
    
    # Fall back to old HTML
    index_path = os.path.join(WEBUI_FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            return f.read()
    return "WebUI not found. Please ensure modules/webui_frontend/dist/index.html exists (run npm run build in modules/webui_frontend).", 404

@app.route("/webui/<path:filename>")
def webui_static(filename):
    """Serve static files from webui_frontend (React build or old files)."""
    # Try React build first
    react_file_path = os.path.join(REACT_BUILD_DIR, filename)
    if os.path.exists(react_file_path) and os.path.isfile(react_file_path):
        return send_from_directory(REACT_BUILD_DIR, filename)

    # Fall back to old files
    file_path = os.path.join(WEBUI_FRONTEND_DIR, filename)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        return send_from_directory(WEBUI_FRONTEND_DIR, filename)
    return "File not found", 404


@app.route("/assets/<path:filename>")
def webui_assets(filename: str):
    """Serve Vite build assets from /assets/*."""
    asset_path = os.path.join(REACT_BUILD_DIR, "assets", filename)
    if os.path.exists(asset_path) and os.path.isfile(asset_path):
        return send_from_directory(os.path.join(REACT_BUILD_DIR, "assets"), filename)
    return "File not found", 404


if __name__ == "__main__":
    port = get_server_port()
    app.run(host="0.0.0.0", port=port)
