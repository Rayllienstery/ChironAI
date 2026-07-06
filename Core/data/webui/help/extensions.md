# Extensions

Extensions package optional capabilities: LLM providers, UI tabs, background workers, and Docker-managed services. They install as folders with a **`chironai-extension.json`** manifest and integrate through documented host contracts — CoreUI is not modified by extensions directly.

## What extensions can do

| Capability | User-visible result |
|------------|---------------------|
| `llm_provider` | New provider in build wizard |
| `tab_ui` / `iframe_tab` | Extra sidebar tab |
| `ui_schema` | Declarative settings/status pages |
| Docker services | Containers started via host Docker runtime |

Extensions **cannot** inject into CoreUI component tree or patch host CSS. They render inside extension runtime containers or iframes.

## Discovery and install

1. Place extension folder in the configured extensions directory (bundled extensions ship under `extensions/bundled/`).
2. Open **Extensions** in the sidebar.
3. Review manifest id, version, type, and capabilities.
4. Enable the extension toggle.
5. Reload WebUI if a new tab should appear (manifest cache refresh).

The registry shows installed vs available, version, and diagnostic messages when manifest validation fails.

## Manifest essentials

Every extension root needs `chironai-extension.json`:

```json
{
  "id": "ollama-provider",
  "version": "1.0.0",
  "type": "llm_provider",
  "title": "Ollama Provider",
  "backend": {
    "entrypoint": "backend.provider:create_provider"
  },
  "capabilities": {
    "docker": true
  }
}
```

Check **`min_host_version`** before upgrading ChironAI — incompatible extensions may fail silently or refuse to start.

## Backend entrypoint

Python backend modules expose:

```python
def create_provider(host_context, manifest):
    return MyProvider(host_context, manifest)
```

`host_context` supplies settings repositories, docker runtime, logging, and other host services. Keep provider logic inside the extension package.

## Docker-managed extensions

Rules from the host contract:

- Extensions **must not** call Docker CLI or `/api/webui/docker/*` themselves
- Declare containers with **`DockerContainerSpec`**
- Start/stop via **`host_context.docker_runtime`**

Use **Docker** tab for host-level container status; use **Extensions** for extension-specific update progress.

## UI extensions

Tab descriptors return metadata consumed by CoreUI:

- `id`, `title`, `icon` or `icon_url`
- Payload may be `iframe` URL or schema-driven UI

Developer mode → **Extension Runtime** tab inspects live extension tabs and actions.

## Operational workflow

### Enable a new provider extension

1. Enable in **Extensions**
2. Wait for Docker health (if applicable)
3. Confirm provider in **LLM Proxy Builds** wizard
4. Create a build pointing at the new provider
5. Test in **Model Tester**, then wire client

### Upgrade

1. Stop dependent builds/clients (or accept brief 503)
2. Replace extension files or pull new version
3. Compare `min_host_version` with **Dashboard** version
4. Run extension migration/update UI if offered
5. Re-verify model list and one proxy call

### Disable / remove

1. Disable toggle — provider disappears from catalog
2. Remove builds that referenced the provider first (avoid orphaned configs)
3. Delete folder only after disable + WebUI restart

## Bundled vs external

| Source | Location | Notes |
|--------|----------|-------|
| Bundled | `extensions/bundled/*` | Offline/bootstrap mirror, trusted |
| External | Your extensions path | Team-owned, separate release cycle |

`ollama-provider` canonical source may live in a dedicated repo; bundled copy is for bootstrap.

## Troubleshooting extensions

| Issue | Action |
|-------|--------|
| Extension not listed | Invalid manifest JSON, wrong folder layout |
| Enable fails | Read **Logs**, check Docker image pull |
| Tab blank | iframe URL unreachable, CORS, or mixed content |
| Provider flaps | Container OOM; inspect Docker logs |

## Related topics

- **Providers** — using extension LLM backends
- **Indexing Content** — some extensions add ingest paths
- **Dev Documentation** (developer mode) — integration guide for authors
- **Troubleshooting** — extension-specific error patterns
