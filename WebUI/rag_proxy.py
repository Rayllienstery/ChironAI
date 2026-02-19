"""
OpenAI-compatible RAG proxy for Zed (and other clients).
Accepts POST /v1/chat/completions, runs RAG (embed -> Qdrant), calls Ollama /api/chat,
returns OpenAI-format response. Listen on 0.0.0.0:8080 for remote access (e.g. Zed on Mac).

Usage:
  On PC: python rag_proxy.py  (after starting Ollama and Qdrant)
  On Mac Zed: OpenAI API Compatible -> API URL: http://<PC_IP>:8080, model: rag-ollama
  Windows firewall: allow inbound on port 8080.

Uses api.http.rag_routes.create_app; prompt and model come from config via application.rag.params.
"""

import logging
import os
import sys

_ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT_DIR not in sys.path:
    sys.path.insert(0, _ROOT_DIR)

from flask import send_from_directory

from config import get_log_level, get_server_port
from api.http.rag_routes import create_app
from api.http.webui_routes import webui_bp

logging.basicConfig(
    level=get_log_level(),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
WEBUI_FRONTEND_DIR = os.path.join(PROJECT_ROOT, "webui_frontend")

app = create_app(webui_dir=BASE_DIR)

# Register WebUI blueprint
app.register_blueprint(webui_bp)

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
    return "WebUI not found. Please ensure webui_frontend/dist/index.html or webui_frontend/index.html exists.", 404

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
