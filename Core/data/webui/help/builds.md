# LLM Proxy Builds

Builds are named configurations that map incoming proxy requests to a model, provider, and optional RAG overlay.

## Create a build

1. Open **LLM Proxy** in the sidebar.
2. Switch to the **Builds** sub-tab.
3. Click **Add build** and fill in the build id, display name, and model.
4. Optionally select a **RAG collection** from the dropdown (requires Qdrant and at least one collection).

## How routing works

Each build exposes a stable id used by clients (`/v1/chat/completions` and related proxy routes). The active build determines provider credentials, model id, and RAG collection override.

## RAG on builds

When a build specifies a collection, it takes precedence over global proxy defaults for that build only. Leave the dropdown empty to inherit global RAG settings.

## Testing

Use **Model Tester** with the same build selected to validate latency, tool calls, and RAG traces before promoting a build to production clients.
