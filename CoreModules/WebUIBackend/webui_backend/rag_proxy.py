"""
OpenAI-compatible RAG proxy for Zed (and other clients).
Accepts POST /v1/chat/completions, runs RAG (embed -> Qdrant), calls Ollama /api/chat,
returns OpenAI-format response. Listen on the configured server port for remote access (e.g. Zed on Mac).

Legacy second listener (build proxy) has been removed. Use the main server port only.

Usage:
  On PC: python rag_proxy.py  (after starting Ollama and Qdrant)
  On Mac Zed: OpenAI API Compatible -> API URL: http://<PC_IP>:<configured_port>

Uses api.http.rag_routes.create_app; prompt and model come from config via application.rag.params.
"""

import logging
import os
import time as _time

from flask import make_response, send_from_directory
from flask_compress import Compress

from config import get_log_level, get_server_port, record_active_server_port
from api.http.rag_routes import create_app
from api.http.startup_timing import process_start_offset_ms, record_phase
from webui_backend.paths import coreui_dir, project_root, webui_data_dir

logging.basicConfig(
    level=get_log_level(),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Werkzeug logs every HTTP request at INFO; hide that noise (errors still use WARNING+).
logging.getLogger("werkzeug").setLevel(logging.WARNING)
_rag_verbose = (os.getenv("RAG_VERBOSE_LOGS", "0") or "").strip().lower() in ("1", "true", "yes", "on")
if not _rag_verbose:
    # Keep cmd output clean: show only warnings/errors for routine RAG and HTTP client operations.
    logging.getLogger("trag.rag").setLevel(logging.WARNING)
    logging.getLogger("llm_proxy").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
BASE_DIR = str(webui_data_dir())
PROJECT_ROOT = str(project_root())
# Frontend: CoreUI (React) under CoreModules
WEBUI_FRONTEND_DIR = str(coreui_dir())

# create_app() registers webui_bp, so /api/webui/* (open-webui/status, start, stop, etc.) is available
_t_create_app = _time.perf_counter()
app = create_app(webui_dir=BASE_DIR)

# Enable transparent brotli/gzip compression for all responses (JS, CSS, JSON, HTML).
# Reduces the 283KB main JS bundle to ~88KB on the wire — ~3× faster first load.
app.config["COMPRESS_REGISTER"] = True
app.config["COMPRESS_LEVEL"] = 6           # gzip level 6 — good speed/ratio balance
app.config["COMPRESS_MIN_SIZE"] = 512      # compress anything > 512 bytes
app.config["COMPRESS_MIMETYPES"] = [
    "text/html",
    "text/css",
    "text/javascript",
    "application/javascript",
    "application/json",
    "application/x-javascript",
    "image/svg+xml",
]
_compress = Compress()
_compress.init_app(app)
# flask_app_init phase is recorded inside create_app(); this outer measurement
# captures total wall-time including the create_app call overhead itself.
_create_app_ms = (_time.perf_counter() - _t_create_app) * 1000

# Pre-warm SessionManager: runs DB schema init and migrations synchronously at startup so
# the very first GET /api/webui/sessions request is fast (no lazy-init overhead on first hit).
_t_session = _time.perf_counter()
_session_status = "ok"
try:
    from infrastructure.database import get_session_manager as _get_session_manager
    _get_session_manager()
except Exception:
    _session_status = "failed"
_session_ms = (_time.perf_counter() - _t_session) * 1000
record_phase(
    phase_id="session_manager",
    label="Session Manager",
    description="SQLite schema initialisation, migrations, and session table setup",
    start_offset_ms=process_start_offset_ms(_t_session),
    duration_ms=_session_ms,
    status=_session_status,
)

# Serve static files from CoreModules/CoreUI
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
            resp = make_response(f.read())
            # Never cache index.html: it references hashed assets and must update after rebuilds.
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            return resp
    
    # Fall back to old HTML
    index_path = os.path.join(WEBUI_FRONTEND_DIR, "index.html")
    if os.path.exists(index_path):
        with open(index_path, "r", encoding="utf-8") as f:
            resp = make_response(f.read())
            resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            resp.headers["Pragma"] = "no-cache"
            return resp
    return "WebUI not found. Please ensure CoreModules/CoreUI/dist/index.html exists (run npm run build in CoreModules/CoreUI).", 404

@app.route("/webui/<path:filename>")
def webui_static(filename):
    """Serve static files from CoreUI (React build or old files)."""
    # Try React build first
    react_file_path = os.path.join(REACT_BUILD_DIR, filename)
    if os.path.exists(react_file_path) and os.path.isfile(react_file_path):
        # Allow caching of hashed files (Vite assets are served under /assets).
        # For safety, prevent caching for any non-asset file under /webui/*.
        resp = send_from_directory(REACT_BUILD_DIR, filename, max_age=0)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp

    # Fall back to old files
    file_path = os.path.join(WEBUI_FRONTEND_DIR, filename)
    if os.path.exists(file_path) and os.path.isfile(file_path):
        resp = send_from_directory(WEBUI_FRONTEND_DIR, filename, max_age=0)
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        resp.headers["Pragma"] = "no-cache"
        return resp
    return "File not found", 404


@app.route("/assets/<path:filename>")
def webui_assets(filename: str):
    """Serve Vite build assets from /assets/*."""
    asset_path = os.path.join(REACT_BUILD_DIR, "assets", filename)
    if os.path.exists(asset_path) and os.path.isfile(asset_path):
        # Vite assets are content-hashed; safe to cache aggressively.
        return send_from_directory(os.path.join(REACT_BUILD_DIR, "assets"), filename, max_age=31536000)
    return "File not found", 404


if __name__ == "__main__":
    port = get_server_port()
    record_active_server_port(port)
    # Allow GET /proxy-trace/current (and other polls) while a long POST /v1/chat/completions runs.
    app.run(host="0.0.0.0", port=port, threaded=True)
