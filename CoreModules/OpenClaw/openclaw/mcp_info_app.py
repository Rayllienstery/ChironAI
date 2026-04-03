"""Lightweight HTTP app on MCP port: health + MCP orientation (not a full MCP server)."""

from __future__ import annotations

from flask import Flask, jsonify


def create_mcp_info_app() -> Flask:
    app = Flask(__name__)

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "openclaw-mcp-info"})

    @app.get("/")
    @app.get("/info")
    def info():
        return jsonify(
            {
                "service": "OpenClaw MCP info",
                "mcp": "Model Context Protocol — IDE connects tools/resources via MCP servers.",
                "vscode": (
                    "VS Code often runs MCP over stdio (child process). "
                    "This HTTP port is for health checks and human-readable notes; "
                    "see docs/OPENCLAW_VSCODE.md and Claw.md in the ChironAI repo root."
                ),
                "openclaw_openai": (
                    "For chat/agent with custom base URL, use the OpenClaw OpenAI-compatible "
                    "port (default 8082), not this MCP info port."
                ),
            }
        )

    return app
