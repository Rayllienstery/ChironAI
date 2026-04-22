# Proxy Phase 0 — Parity checklist (OpenAI-compatible)

Goal: verify `/v1/chat/completions` behaves as a stable OpenAI-compatible mediator and does **not** silently enable enrichment.

## 1) Test inputs (keep constant)

- Same Zed provider: `openai_compatible` pointing at the proxy `/v1`.
- Same model name and settings in Zed for the request.
- Same prompt / same file attachment / same selection.
- Run each case twice to rule out transient upstream issues.

Recommended cases:

1) **Plain chat**: small prompt, no tools.
2) **Tool-capable chat**: prompt that would normally expose tools in Zed (but should not force Ollama native tools).
3) **File description**: “describe file @path” with file attached.

## 2) Expected Proxy Trace fields (schema v0)

In Proxy Trace (Live or exported markdown), verify:

- **Models**
  - `Model (Ollama)` matches the concrete Ollama tag you expect.
  - `Requested model` matches what Zed sent.

- **Features**
  - `schema_version` is present (e.g. `proxy_trace_v0`).
  - `proxy_pipeline` is present.
  - In mediator mode (primitive passthrough):
    - `rag_enabled = No`
    - `web_enabled = No`
    - `native_tools_enabled = No`
    - `collection_selected = No`
    - `rag_retrieval_skipped = Yes`

- **Steps**
  - No unexpected retrieval steps (no `embed/search/rerank/total_rag`) in mediator mode.

## 3) Behavioral parity checks (OpenAI-compatible)

For each case:

- Output is coherent (no single-token placeholders like `.`, `)`, `!`).
- Streaming does not abort (no unexpected EOF / chunk errors).
- Tool flows remain usable in Zed:
  - Zed receives valid OpenAI-compatible `tool_calls` when appropriate (in-band tool prompting path).
  - The proxy does not switch to Ollama native tools unless explicitly enabled in a later phase.

## 4) Regression tripwires (must fail the check)

Treat any of these as a Phase-0 failure:

- `features.rag_enabled` becomes `Yes` without an explicit opt-in flag.
- RAG steps appear during mediator mode.
- `native_tools_enabled` flips to `Yes` without explicit opt-in.
- Model output degenerates (placeholder-only, micro-garbage) compared to baseline runs.

