"""
OpenAI-compatible RAG proxy for IDE clients.
Accepts POST /v1/chat/completions, runs RAG (embed -> Qdrant), calls the
provider runtime, and returns an OpenAI-format response. Listen on the
configured server port for remote access.

Legacy second listener (build proxy) has been removed. Use the main server port only.

Usage:
  On PC: python -m webui_backend.rag_proxy  (after starting Qdrant and a provider extension)
  On Mac Zed: OpenAI API Compatible -> API URL: http://<PC_IP>:<configured_port>

Uses webui_backend.app_factory.create_production_app; prompt and model come from
provider/runtime settings via rag_service.application.params.
"""

import logging
import os

from config import get_log_level, get_server_host, get_server_port, record_active_server_port
from webui_backend.app_factory import create_production_app
from webui_backend.paths import project_root, webui_data_dir

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

app = create_production_app(webui_dir=BASE_DIR)


if __name__ == "__main__":
    from webui_backend.open_browser_when_ready import open_browser_when_ready

    port = get_server_port()
    record_active_server_port(port)
    webui_url = f"http://127.0.0.1:{port}/webui"
    print(f"Starting backend on port {port}...", flush=True)
    print(f"WebUI: {webui_url}", flush=True)
    open_browser_when_ready()
    try:
        import logging as _logging

        from waitress import serve as _waitress_serve

        # Waitress is a production-grade WSGI server — much faster than Werkzeug on Windows.
        _logging.getLogger("waitress").setLevel(_logging.WARNING)
        _waitress_serve(
            app,
            host=get_server_host(),
            port=port,
            threads=8,
            channel_timeout=120,
            cleanup_interval=10,
        )
    except ImportError:
        app.run(host=get_server_host(), port=port, threaded=True)
