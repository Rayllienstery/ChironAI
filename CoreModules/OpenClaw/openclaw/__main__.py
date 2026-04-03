"""Run OpenClaw HTTP servers (OpenAI port + optional MCP info port)."""

from __future__ import annotations

import logging
import os
import sys
import threading

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_OPENCLAW = os.path.join(_ROOT, "CoreModules", "OpenClaw")
if _OPENCLAW not in sys.path:
    sys.path.insert(0, _OPENCLAW)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    os.environ.setdefault("CHIRONAI_WEBUI_DIR", os.path.join(_ROOT, "WebUI"))

    from config import (
        get_openclaw_host,
        get_openclaw_mcp_http_enabled,
        get_openclaw_mcp_port,
        get_openclaw_openai_port,
        get_openclaw_trace_buffer_size,
    )
    from werkzeug.serving import make_server

    from openclaw.http_server import create_openclaw_flask_app
    from openclaw.mcp_info_app import create_mcp_info_app
    from openclaw.trace_store import configure as trace_configure

    trace_configure(get_openclaw_trace_buffer_size())
    host = get_openclaw_host()
    oa = get_openclaw_openai_port()
    app = create_openclaw_flask_app()
    srv = make_server(host, oa, app, threaded=True)
    logging.getLogger(__name__).info("OpenClaw OpenAI API http://%s:%s/v1/chat/completions", host, oa)
    if get_openclaw_mcp_http_enabled():
        mp = get_openclaw_mcp_port()
        mapp = create_mcp_info_app()
        srv2 = make_server(host, mp, mapp, threaded=True)
        threading.Thread(target=srv2.serve_forever, name="openclaw_mcp", daemon=True).start()
        logging.getLogger(__name__).info("OpenClaw MCP info http://%s:%s/", host, mp)
    srv.serve_forever()


if __name__ == "__main__":
    main()
