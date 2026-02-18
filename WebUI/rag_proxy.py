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

from config import get_log_level, get_server_port
from api.http.rag_routes import create_app

logging.basicConfig(
    level=get_log_level(),
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = create_app(webui_dir=BASE_DIR)


if __name__ == "__main__":
    port = get_server_port()
    app.run(host="0.0.0.0", port=port)
