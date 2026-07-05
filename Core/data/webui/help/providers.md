# Providers

Providers supply models and credentials to the LLM proxy layer.

## Built-in vs extensions

Core providers (e.g. Ollama-compatible endpoints) ship with ChironAI. Additional providers may arrive via **Extensions** with their own manifests and Docker services.

## Configuration

Provider settings are stored in WebUI configuration and extension manifests. After changing credentials or base URLs, restart affected extension containers if prompted on the **Extensions** tab.

## Model listing

**Dashboard** and build wizards call `/api/webui/models` (and proxy model listing) to populate dropdowns. If a model is missing, verify the provider is healthy in **Dependencies** or extension runtime status.

## Proxy compatibility

The proxy exposes OpenAI-compatible routes (`/v1/chat/completions`, `/v1/responses`, etc.). Point external clients at the WebUI host and port with the correct build or default routing.
