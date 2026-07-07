# Troubleshooting

Symptom-first guide for operators. Always note: **build id**, **proxy key prefix**, **Chiron version** (header), and timestamp when asking for help.

## WebUI will not start

**Symptoms:** blank page, connection refused, immediate exit.

1. Read `logs/webui_errors.log` (tail last 50 lines).
2. **Dependencies** — missing Python/npm packages?
3. **Settings → Server port** — port already in use? Change port and restart.
4. CoreUI build missing — run `npm run build` in `CoreModules/CoreUI` for dev setups.
5. Windows: run launcher from repo root so relative paths resolve.

## CoreUI loads but API calls fail

**Symptoms:** red errors, “Failed to fetch”, empty tabs.

1. Confirm browser URL matches server port (not stale bookmark).
2. Check browser devtools Network — 502/503 on `/api/webui/*`?
3. Restart WebUI; watch terminal for traceback.
4. CORS usually not an issue for same-origin CoreUI — suspect server down.

## Empty model or provider list

**Symptoms:** build wizard provider dropdown empty or model list blank.

| Check | Fix |
|-------|-----|
| Extension disabled | **Extensions** → enable provider extension |
| Ollama/container stopped | **Docker** → start service |
| Wrong base URL in extension config | Fix URL, restart container |
| Provider slow | Wait 30s, refresh wizard |
| Auth to cloud provider | Update API key in extension settings |

Validate with **Dependencies** and extension runtime logs.

## Proxy 401 Unauthorized

- Client missing `Authorization: Bearer` or `x-api-key`
- Typo or trailing whitespace in key
- Key rotated in UI but not in IDE config

**Fix:** **RAG Fusion Proxy → Security → Reveal key**, update client, retry curl from **Proxy Clients & API**.

## Proxy 503 server_configuration_error

No proxy API key configured on server.

**Fix:** Generate key in Security panel before any `/v1` call.

## Unknown or invalid model (4xx)

- Client `model` must equal **build id** exactly
- Build deleted but client cache stale — refresh model list
- Client using raw Ollama tag instead of build id

**Fix:** `GET /v1/models`, pick listed id, update client config.

## RAG returns no context

1. **RAG tab retrieval test** — if empty, indexing or collection problem
2. If retrieval hits but chat doesn’t — trigger threshold too high; ask technical question
3. **Trace `collection_source`** — wrong precedence layer
4. Qdrant down — **Dashboard** / **RAG** health
5. Embed model mismatch after reindex — re-index collection

## RAG returns irrelevant context

- Collection too broad — split collections
- Chunk size too large — re-index with smaller chunks
- Enable rerank / hybrid if disabled
- Review concept aliases and domain config (`docs/RAG_BEHAVIOR.md`)

## Streaming hangs or cuts off

- Client timeout < server generation time — increase client timeout
- Provider OOM — check Ollama/GPU logs
- Compare streaming vs non-stream in **Model Tester**
- Network middleboxes buffering SSE — test curl stream locally

## Vision / image errors

| Message | Cause | Fix |
|---------|-------|-----|
| `Cannot read "image.png"` in user content | Client failed to embed file | Configure client modalities; use data URL |
| `Image omitted: Responses file_id` in user content | Client sent `input_image.file_id` | Use inline `image_url` / data URL instead |
| Model does not support image | Text-only upstream tag | Set build vision fallback or vision model |
| Empty response with image | Tools+vision conflict | Expected suppression — split turns |

See LlmProxy README vision section and **Proxy Clients & API**.

## Qdrant connection refused

- Container not running (**Docker**)
- Wrong host/port in host config (default 6333)
- Firewall blocking localhost from service account

**Fix:** start Qdrant, verify `http://127.0.0.1:6333/collections` from server host.

## Extension fails to start

- Read **Logs** and Docker container logs
- Manifest `min_host_version` > host version
- Port conflict on extension container
- Image pull failure (offline machine — use bundled images)

## Crawler/index job stuck

- Check disk space
- Path permission denied — fix mount/ACL
- Cancel and rerun with smaller scope
- Inspect crawler stderr in **Logs**

## Performance degradation

- Qdrant collection too large for RAM — scale or prune
- Concurrent embedding jobs — serialize
- Debug logging verbose — reduce poll intervals in **Settings**
- Journal DB huge — purge old entries if UI offers

## Diagnostic data to collect

Before escalating:

```
Chiron version: (from header)
Build id:
Collection (expected vs trace):
Client tool + version:
HTTP status + response body snippet:
Journal id or trace id (from Logs):
Relevant webui_errors.log excerpt:
Steps to reproduce:
```

## Still stuck?

- **Help** articles: follow learning path from **Getting Started**
- Developer mode → **Dev Documentation**, **Swagger** for HTTP contracts
- Repository: `docs/ARCHITECTURE.md`, `docs/RAG_BEHAVIOR.md`, `CoreModules/LlmProxy/README.md`
