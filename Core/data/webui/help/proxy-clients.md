# Proxy Clients & API

External tools connect to ChironAI through the **RAG Fusion Proxy** HTTP API on the same host/port as the WebUI (unless reverse-proxied). All `/v1/*` routes require the **proxy API key** from **RAG Fusion Proxy → Overview → Security**.

## Authentication

Send the key using either header:

```
Authorization: Bearer YOUR_PROXY_KEY
```

or

```
x-api-key: YOUR_PROXY_KEY
```

| HTTP | Meaning |
|------|---------|
| 503 + `server_configuration_error` | No key configured on server — generate one |
| 401 + `authentication_error` | Missing or wrong key |
| 200 / streamed 200 | Key accepted |

Regenerating the key invalidates the previous key immediately — update all clients.

## Base URL

```
http://<host>:<port>/v1/
```

Find `<port>` on **Dashboard** or **Settings → Server port**. Use `127.0.0.1` for local-only clients.

## Core endpoints

| Method | Path | Use case |
|--------|------|----------|
| GET | `/v1/models` | List build ids (OpenAI/Anthropic shapes) |
| POST | `/v1/chat/completions` | OpenAI chat — Cursor, Kilo, many SDKs |
| POST | `/v1/responses` | OpenAI Responses — OpenCode |
| POST | `/v1/messages` | Anthropic Messages API |
| POST | `/v1/files/apply-edit` | Agent file edits (when enabled) |

Always set `"model": "<build-id>"` to a build defined in **LLM Proxy Builds**.

## curl smoke test

```bash
export CHIRON_BASE=http://127.0.0.1:8080
export CHIRON_KEY=your_key_here
export CHIRON_BUILD=dev-main

curl -s "$CHIRON_BASE/v1/chat/completions" \
  -H "Authorization: Bearer $CHIRON_KEY" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"$CHIRON_BUILD\",
    \"messages\": [{\"role\": \"user\", \"content\": \"Say hello in one sentence.\"}]
  }"
```

Streaming: add `"stream": true` and consume SSE lines (`data: {...}`).

## Cursor / VS Code style clients

Typical OpenAI-compatible settings:

- **Base URL**: `http://127.0.0.1:<port>/v1`
- **API key**: Chiron proxy key (not OpenAI’s)
- **Model**: build id exactly as in **LLM Proxy Builds**

If the client caches models, refresh after adding builds. Use **Model Tester** first to confirm the build works server-side.

## OpenCode

OpenCode often uses **`POST /v1/responses`** with `input` items (`input_text`, `input_image`).

Vision clients must declare image modalities or attachments may be stripped **before** reaching Chiron. Regenerate config from WebUI builds:

```bash
python scripts/configure_opencode_chiron_vision.py
```

Pick a vision-capable build under the generated provider entry. Restart OpenCode after config changes.

## Anthropic-compatible clients

Call `POST /v1/messages` with header:

```
anthropic-version: 2023-06-01
```

Model field should still be your **build id**. The proxy translates into the internal chat pipeline (RAG, tools, streaming).

## Optional request fields (RAG)

Override collection per request (wins over build default):

```json
{
  "model": "dev-main",
  "collection_name": "ios-docs",
  "messages": [...]
}
```

Inspect trace metadata for `collection_source` to confirm which layer applied.

## Vision / images

Supported in user messages as OpenAI multipart content:

```json
{
  "role": "user",
  "content": [
    { "type": "text", "text": "Describe this screenshot" },
    {
      "type": "image_url",
      "image_url": { "url": "data:image/png;base64,...." }
    }
  ]
}
```

- Prefer **base64 data URLs** — remote `http(s)` URLs are not fetched by default
- Build should use vision-capable model or configured fallback
- Client-side errors like `Cannot read "image.png"` mean the IDE never embedded the file — fix client config, not the proxy

## Open WebUI as a client

Open WebUI is a separate product. When pointing it at Chiron:

- Set OpenAI API base to `http://host:port/v1`
- Use **Chiron proxy key** as the OpenAI API key
- Open WebUI auth does **not** replace Chiron key for direct `/v1` access

## Rate, timeout, and streaming

- Long RAG + large models may exceed client timeouts — increase client read timeout
- Streaming reduces time-to-first-token; non-streaming waits for full completion
- Journal logging (unless build ephemeral mode) adds small SQLite write overhead

## Security checklist

- [ ] Proxy key generated and not committed to git
- [ ] Server bound to localhost if single-user dev machine
- [ ] Reverse proxy adds TLS in remote deployments
- [ ] Separate builds/keys for prod vs experiment when sharing a host

## Related topics

- **Getting Started** — first build and key
- **LLM Proxy Builds** — model ids clients must use
- **Logs & Debugging** — trace ids from client errors
- **Troubleshooting** — 401/503, streaming, vision
