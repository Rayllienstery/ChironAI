# Troubleshooting

Common issues and where to look first.

## WebUI will not start

- Check **Logs** (`logs/webui_errors.log` on disk).
- Run dependency checks on the **Dependencies** tab.
- Verify the configured port is free (see **Settings**).

## Models list is empty

- Confirm the provider service (Ollama, extension container, etc.) is running.
- Open **Dependencies** for connectivity hints.
- Review proxy logs for authentication errors.

## RAG returns no context

- Verify Qdrant health and collection name spelling.
- Check build-level vs global collection precedence.
- Run a retrieval test on the **RAG** tab with the same query.

## Proxy 4xx/5xx from clients

- Match the client’s model/build id to an existing build.
- Enable request logging on **Logs** and inspect proxy journal entries.
- For streaming issues, test with **Model Tester** before external clients.

## Still stuck?

Capture the error text, active build id, and relevant log lines. Developer documentation under **Dev Documentation** (developer mode) links to API reference and architecture notes.
