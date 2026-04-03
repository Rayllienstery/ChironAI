# OpenClaw (ChironAI Core Module)

Agent layer: OpenAI-compatible `/v1/chat/completions` on a dedicated port, optional MCP info HTTP, RAG `rag_query` tool, in-memory traces.

Install editable (from repo root):

```bash
pip install -e CoreModules/OpenClaw
```

Run standalone (expects `chironai` on `PYTHONPATH` and `CHIRONAI_WEBUI_DIR`):

```bash
set CHIRONAI_WEBUI_DIR=C:\path\to\AI\WebUI
python -m openclaw
```

See [Claw.md](../../Claw.md) at repository root for full documentation.
