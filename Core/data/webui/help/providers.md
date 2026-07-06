# Providers

Providers are pluggable backends that supply **models** and **credentials** to ChironAI. The WebUI never calls Ollama or cloud APIs directly from the browser — everything goes through server-side **provider runtime** + **LLM Proxy** wiring.

## Provider types

| Type | Typical example | How it appears |
|------|-----------------|----------------|
| Extension LLM provider | `ollama-provider` | **Extensions** tab, provider catalog |
| Bundled / host wiring | Internal adapters | **Dependencies**, build wizard provider list |
| Cloud via extension | Custom API gateways | Extension manifest + Docker service |

The canonical Ollama integration is the **`ollama-provider` extension** (bundled mirror under `extensions/bundled/ollama-provider`). Core proxy routes do not expose raw Ollama `/api/chat` — use the extension or `/v1/chat/completions` through a build.

## Provider catalog in the WebUI

**LLM Proxy Builds** wizard → **Provider** dropdown is populated from the live catalog:

- Extension id and human title
- Available models for the selected provider
- Health implied by successful model listing (empty list = misconfiguration or offline service)

**Dashboard** and `/api/webui/models` feed other pickers (RAG embed models, etc.).

## Configuration checklist

For each provider you rely on:

1. **Extension enabled** — **Extensions** → toggle on, check version vs host `min_host_version`
2. **Docker service running** — **Docker** or extension runtime status (if extension uses containers)
3. **Credentials** — API keys, base URLs in extension settings or env (never in CoreUI localStorage)
4. **Model visible** — select provider in build wizard; models should populate within a few seconds
5. **Network** — WebUI host can reach provider host:port (firewall, WSL, Docker network)

After credential or URL changes, restart the extension container when the UI prompts you.

## Extension provider contract

Extension LLM providers implement `create_provider(host_context, manifest)` and expose capabilities declared in `chironai-extension.json`:

```json
{
  "id": "my-provider",
  "version": "0.1.0",
  "type": "llm_provider",
  "title": "My Provider",
  "backend": { "entrypoint": "backend.provider:create_provider" }
}
```

The host injects `host_context` (settings, docker runtime, logging). Extensions must **not** shell out to Docker directly — use `host_context.docker_runtime` and `DockerContainerSpec`.

## Models: listing vs using

- **Listing** — `GET /api/webui/models`, build wizard, RAG model pickers
- **Using** — always through a **build** (or explicit proxy path) on `/v1/chat/completions`

Model ids are provider-specific strings (Ollama tags, API model names). Copy ids from the wizard dropdown, not from unrelated client configs.

## Vision-capable models

OpenAI-style multimodal requests (`image_url` parts) require a vision-capable upstream model. The proxy:

- Advertises vision support on `/v1/models` rows for builds
- May **fallback** to `vision_model` on the build or env `LLM_PROXY_VISION_FALLBACK_MODEL` when the primary tag lacks vision
- Suppresses tools on image turns when the upstream rejects tools+vision together

Images must usually be `data:image/...;base64,...` URLs unless `LLM_PROXY_VISION_FETCH_EXTERNAL_URLS=1` (trusted environments only).

## Provider vs proxy vs build

| Layer | Responsibility |
|-------|------------------|
| **Provider** | Talks to Ollama/OpenAI/etc.; raw generation |
| **LLM Proxy** | OpenAI/Anthropic HTTP surface, RAG orchestration, tools |
| **Build** | Named bundle: provider + model + RAG + params |

Clients should target **build ids**, not raw provider model strings, unless you have a deliberate exception.

## Health diagnostics

| Symptom | Likely cause |
|---------|----------------|
| Empty provider dropdown | No extensions registered or host failed to load catalog |
| Provider listed, zero models | Service down, wrong base URL, auth failure |
| Models in UI, proxy 502 | Provider timeout, model pulled but not loaded in Ollama |
| Intermittent failures | GPU OOM, container restart, rate limits |

Check **Dependencies** for declared versions, **Logs** for stack traces, extension container logs in **Docker**.

## Security notes

- Provider API keys live server-side (settings DB, extension config, env)
- The **proxy API key** (RAG Fusion Security) protects `/v1/*` from anonymous LAN access
- Open WebUI has separate auth — configuring Open WebUI against Chiron still requires the Chiron proxy key on the OpenAI provider entry

## Related topics

- **Extensions** — install and lifecycle
- **LLM Proxy Builds** — bind provider+model to a build id
- **Proxy Clients & API** — how external tools authenticate
- **Troubleshooting** — empty model list, 401/503 errors
