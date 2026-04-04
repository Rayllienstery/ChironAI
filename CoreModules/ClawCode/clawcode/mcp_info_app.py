"""Lightweight HTTP app on MCP port: health + MCP orientation (not a full MCP server)."""

from __future__ import annotations

from flask import Flask, jsonify


def create_mcp_info_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "clawcode-mcp-info"})

    @app.get("/")
    @app.get("/info")
    def info():
        return jsonify(
            {
                "service": "ClawCode MCP info",
                "mcp": "Model Context Protocol — IDE connects tools/resources via MCP servers.",
                "vscode": (
                    "VS Code often runs MCP over stdio (child process). "
                    "This HTTP port is for health checks and human-readable notes; "
                    "see docs/CLAWCODE_VSCODE.md and Claw.md in the ChironAI repo root."
                ),
                "clawcode_openai": (
                    "For chat/agent with custom base URL, use the ClawCode port (default 8082): "
                    "OpenAI POST /v1/chat/completions or Anthropic POST /v1/messages — not this MCP info port."
                ),
            }
        )

    return app
