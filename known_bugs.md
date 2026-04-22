# Known bugs and workarounds

## LLM Proxy: OpenAI-style SSE streaming vs single-chunk SSE

### Symptom

Some clients (e.g. IDE agents with native tools and large contexts) misbehave when the proxy streams the assistant response **token-by-token** over Server-Sent Events (SSE): the session may appear to stop mid-turn, tool calls may not arrive, or the UI never reaches a clean “done” state. The same model and build often work reliably when the assistant payload is delivered in **one burst** of SSE chunks (full content and/or tool calls, then `finish_reason`, then `[DONE]`).

### Cause (high level)

True streaming from Ollama (`/api/chat` with `stream: true`) produces many incremental NDJSON lines; the proxy maps them to OpenAI-shaped `chat.completion.chunk` events. Edge cases include stream termination before a final `done` line, client parsers that assume different chunk ordering, and models that only attach `tool_calls` on the last merged message. Those issues do not apply when Ollama is called **once** with `stream: false` and the proxy **synthesizes** a short SSE sequence.

### Workaround (supported)

Per **LLM Proxy → Builds → Edit build**, turn **off** **Token-by-token SSE streaming** (build field `sse_streaming: false`). Clients can still send `stream: true`; the proxy keeps `Content-Type: text/event-stream` but performs a single non-streaming Ollama call and emits one logical response as a few SSE events (role, full `content` or `tool_calls`, final chunk, `[DONE]`).

### Implementation reference

- Build flag: `sse_streaming` in `application/llm_proxy_builds.py` (default `true`).
- Handler: `CoreModules/LlmProxy/llm_proxy/chat_completions.py` — branches on `build_sse_streaming` for native-tools and plain chat paths; trace keys `request.build_sse_streaming`, `request.sse_single_chunk`, `ollama.chat_stream`.

### Status

Workaround shipped; root causes of fragile token streaming (client, Ollama, or proxy merge logic) may still be investigated separately.

## LLM Proxy: single-chunk SSE vs “agent stops in the same place”

**Single-chunk SSE only fixes transport.** When the build disables token-by-token streaming (`sse_streaming: false`), the proxy still asks Ollama once and maps the result to a short SSE sequence. If the trace shows `sse_single_chunk: true` but `tool_calls_count` stays `0` and the assistant message is plain prose, the model ended the turn with a normal completion (no tools)—the same logical outcome as a non-streaming JSON response.

Use the trace’s Ollama fields (e.g. `response.ollama_done_reason`, `response.ollama_eval_count`) to distinguish **`stop`** (model chose to finish in text) from **`length`** (output cap / truncation). Also check whether the client sent `max_tokens` (mapped to Ollama `num_predict`), context size, tool count, and prior tool errors; those often explain repeated “stops” that look like the same step every time.
