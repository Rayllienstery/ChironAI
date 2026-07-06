# Logs & Debugging

When answers look wrong, latency spikes, or clients fail mysteriously, use the **Logs** tab plus on-disk files. ChironAI records proxy activity at two levels: **live traces** (in-memory, recent) and **RAG Fusion Journal** (SQLite, persisted).

## Logs tab layout

| Sub-area | Contents |
|----------|----------|
| **Traces** | In-flight and recent proxy traces with step timeline |
| **RAG Fusion Journal** | Completed requests stored in `logs/webui.db` |
| Filters | Time range, search, detail modal |

Open a journal entry to inspect full metadata JSON: user query, response preview, `trace`, `rag_steps`, token-ish stats.

## What gets persisted

Default behaviour writes INFO-level proxy journal rows:

- `session_id = proxy`
- User message (truncated to 500 chars in stored preview)
- Response preview
- Rich `metadata.trace` for multi-step flows (RAG, tools)

**Ephemeral mode** on a build skips journal writes — useful for bulk automation, bad for debugging. Toggle in build wizard advanced step.

## Trace fields worth reading

When expanding a trace or journal metadata:

| Field | Meaning |
|-------|---------|
| `collection_name` | Qdrant collection used |
| `collection_source` | Which precedence rule picked it |
| `rag_steps` | Retrieval sub-steps timing/outcome |
| `images_count` | Vision payloads forwarded (not raw base64) |
| Provider/backend | Which adapter served the request |

Compare **Model Tester** inline trace with **Logs** entry for the same prompt if UI truncates.

## Debugging workflow

1. **Reproduce in Model Tester** with the same build id as the client
2. If Tester works but client fails → key, base URL, model name, or client stripping attachments
3. If Tester fails → provider, RAG, or build config
4. Open **Logs → Journal** for the matching timestamp
5. For retrieval issues, cross-check **RAG tab** retrieval test with identical query text

## On-disk log files

| Path | When to read |
|------|----------------|
| `logs/webui_errors.log` | WebUI startup, route exceptions |
| `logs/webui.db` | Journal source (do not edit live) |
| Terminal / service stdout | Extension workers, startup smoke |

Rotate or archive large error logs before sharing externally — they may contain paths or prompts.

## Live notifications

CoreUI notification center surfaces long-running dependency updates and some proxy completion events. Use for “job finished” awareness; deep inspection still belongs in **Logs**.

## Proxy Logs analytics

When enabled in your deployment, analytics views aggregate journal history (latency distributions, volume). Use for trends; use journal detail for single-request forensics.

## Internal agent access (LogsManager)

Python agents inside the repo can query the journal programmatically (`LogsManager`) — not exposed via WebUI HTTP. Operators should use **Logs** tab instead.

## Common patterns

### “Client got 401”

Key mismatch or missing header. Regenerate only if compromise suspected — otherwise copy from Security panel.

### “Empty journal”

Ephemeral build, wrong time filter, or requests hitting a different port/instance.

### “Trace shows RAG skipped”

Trigger score below threshold — rephrase with technical terms or lower threshold in settings.

### “Trace shows collection X, expected Y”

Walk precedence table in **RAG Collections**; check client `collection_name` override.

## Hygiene

- Periodically purge old journal rows from UI if disk grows (destructive — confirm backup)
- Do not share journal exports without redacting API keys and private doc snippets
- Enable developer mode for **Dev Documentation** and Swagger when building custom integrations

## Related topics

- **Troubleshooting** — symptom → fix index
- **RAG Collections** — precedence and trigger logic
- **LLM Proxy Builds** — ephemeral flag
- **Proxy Clients & API** — auth headers
