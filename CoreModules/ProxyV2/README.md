# Proxy V2

Thin HTTP mediator between IDE clients and upstream Ollama on a separate port (default 8081). Implements URL parity with the main `llm_proxy` v1 blueprint while keeping LLM semantics equivalent to calling Ollama directly, plus an in-memory request trace for WebUI.

Install editable from repo root:

```bash
pip install -e CoreModules/ProxyV2
```

The host application (`WebUI/rag_proxy.py`) starts this Flask app in a background thread and supplies `ProxyV2Wiring` (Ollama URLs, optional pinned model, OpenAI format bridge, host delegates for Chiron-only routes).

## Sampling options and tools behavior

### Sampling options (temperature / top_p / max tokens)

Proxy V2 accepts OpenAI-shaped chat bodies on `/v1/chat/completions`. For `chat_v1` it now maps a subset of sampling options from the client onto Ollama options:

- `temperature` → `options.temperature`
- `top_p` → `options.top_p`
- `max_completion_tokens` (or `max_tokens`) → `options.num_predict`

These values are merged **on top of** the host defaults returned by `get_ollama_chat_options()`. This means:

- host-level config still defines sensible defaults and limits,
- a client (IDE) can override them per-request.

The legacy `/v1/completions` endpoint already applied similar mapping via `_openai_to_ollama_generate_body`; chat and completions are now consistent.

### Native tools vs. plain chat

When the client sends `tools` and does not force `tool_choice: "none"`, Proxy V2 runs in **native tools mode**:

- OpenAI tool definitions are forwarded to Ollama;
- Proxy V2 calls Ollama `/api/chat` with `stream: false`, then maps the final `message` to OpenAI (including `tool_calls`). If the client asked for `stream: true`, the proxy still returns SSE by synthesizing chunks from that single response.

For simpler question-answering over text (for example, “о чем файл” with inline context), native tools are often unnecessary overhead for small models.

To control this behavior:

- If the client sets `tool_choice: "none"` or omits tools, Proxy V2 falls back to **plain chat** (no native tools).
- You can force native tools off at the host level by setting:

  ```bash
  export PROXY_V2_DISABLE_NATIVE_TOOLS=1
  ```

In plain-chat mode, Proxy V2 still forwards the same `messages` and sampling options, but does not attach `tools`/`tool_choice` to the Ollama payload.

### Ollama `stream` flag

Upstream `/api/chat` requests from Proxy V2 use **`"stream": false`** so Ollama returns one complete JSON payload. OpenAI-compatible **`stream: true`** on the client is honored by emitting **synthesized** SSE chunks after the full reply is available (token-by-token streaming from Ollama is not used on this path).
