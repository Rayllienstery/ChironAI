"""Run ClawCode HTTP servers (OpenAI port + optional MCP info port)."""

from __future__ import annotations

import logging
import os
import sys
import threading

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
_CLAWCODE = os.path.join(_ROOT, "CoreModules", "ClawCode")
if _CLAWCODE not in sys.path:
    sys.path.insert(0, _CLAWCODE)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    os.environ.setdefault("CHIRONAI_WEBUI_DIR", os.path.join(_ROOT, "WebUI"))

    from config import (
        get_clawcode_host,
        get_clawcode_mcp_http_enabled,
        get_clawcode_mcp_port,
        get_clawcode_openai_port,
        get_clawcode_trace_buffer_size,
    )
    from werkzeug.serving import make_server

    from clawcode.http_server import create_clawcode_flask_app
    from clawcode.mcp_info_app import create_mcp_info_app
    from clawcode.trace_store import configure as trace_configure

    trace_configure(get_clawcode_trace_buffer_size())
    host = get_clawcode_host()
    oa = get_clawcode_openai_port()
    app = create_clawcode_flask_app()
    srv = make_server(host, oa, app, threaded=True)
    logging.getLogger(__name__).info(
        "ClawCode OpenAI + Anthropic API http://%s:%s/v1/chat/completions | /v1/messages",
        host,
        oa,
    )
    if get_clawcode_mcp_http_enabled():
        mp = get_clawcode_mcp_port()
        mapp = create_mcp_info_app()
        srv2 = make_server(host, mp, mapp, threaded=True)
        threading.Thread(target=srv2.serve_forever, name="clawcode_mcp", daemon=True).start()
        logging.getLogger(__name__).info("ClawCode MCP info http://%s:%s/", host, mp)
    srv.serve_forever()


if __name__ == "__main__":
    main()
