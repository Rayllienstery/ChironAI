# OllamaInteractor

Standalone **CLI** that speaks to the [Ollama](https://ollama.com/) HTTP API. The main ChironAI / tmrag application is expected to call this tool **only via subprocess** (no `import ollama_interactor` in the host app), so all Ollama REST traffic lives in one process boundary.

## Why this exists

- **Single place for Ollama HTTP**: The monolith previously issued `requests` to `localhost:11434` (and friends) from many files (`infrastructure/ollama`, `webui_routes`, WebUI backend ingest scripts, RAG submodules). That spreads timeouts, error handling, and API quirks everywhere.
- **Explicit contract**: stdin/stdout JSON (and NDJSON for streaming) is easy to test, log, and swap for another implementation later (different language, gRPC, etc.) without touching domain logic.
- **Process isolation**: A failure or heavy response handling stays inside the helper process; the host can enforce global timeouts and capture stderr uniformly.

## Why subprocess (trade-offs)

**Pros**

- No Python import coupling between the repo root and this package.
- You can replace `ollama_interactor` with a compatible CLI without changing call sites.
- Clear separation for packaging (optional editable install, or `PYTHONPATH` only).

**Cons**

- **Per-call overhead**: Starting a process has a fixed cost. Mitigation: one subprocess per logical operation; for chat streaming, **one** long-lived subprocess per request, reading NDJSON lines until the stream ends (not one process per chunk).
- **Large payloads**: Always pass big bodies on **stdin**, not argv, to avoid OS command-line limits (especially on Windows).
- **Debugging**: Use `-v` / `--verbose` on the CLI and inspect stderr JSON on errors.

## Installation

### Option A — Editable install (recommended for development)

From the repository root:

```bash
pip install -e CoreModules/OllamaInteractor
```

Then `python -m ollama_interactor` and the `ollama-interactor` console script resolve without extra `PYTHONPATH`.

### Option B — No install (source on PYTHONPATH)

Ensure the package directory is on `PYTHONPATH` (the folder that **contains** the `ollama_interactor` package, i.e. `CoreModules/OllamaInteractor`):

```bash
# Linux/macOS
export PYTHONPATH="/path/to/repo/CoreModules/OllamaInteractor:$PYTHONPATH"
python -m ollama_interactor ping --base-url http://localhost:11434
```

The host app’s `cli_runner` (in the main repo) prepends this path automatically when it detects a checkout layout with `CoreModules/OllamaInteractor/ollama_interactor`.

## Environment variables

| Variable | Purpose |
|----------|---------|
| `OLLAMA_BASE_URL` | Default base URL for `tags` and `ping` (default `http://localhost:11434`) |
| `OLLAMA_INTERACTOR_CMD` | **Host repo**: overrides how the parent process invokes this CLI (see main repo docs / `cli_runner.py`) |

This package does **not** read the main app’s `config/` or `models.yaml`; the caller passes full URLs and bodies.

## Subcommands

### `tags`

`GET {base}/api/tags`

```bash
ollama-interactor tags --base-url http://localhost:11434
```

Stdout: single JSON object (Ollama response). Stderr: JSON error object on failure. Exit code non-zero on error.

### `ping`

Lightweight reachability check (`GET /api/tags`).

```bash
ollama-interactor ping --base-url http://localhost:11434
```

Stdout: `{"ok": true, "status_code": 200}` or similar.

### `embed`

`POST` to the URL you provide (typically `.../api/embed`).

**Stdin JSON:**

```json
{
  "url": "http://localhost:11434/api/embed",
  "json": {
    "model": "mxbai-embed-large",
    "input": "hello"
  },
  "timeout": 120
}
```

For batch embedding, set `"input": ["a", "b"]` per Ollama’s API.

Stdout: single JSON (Ollama response). The `json` field may be spelled `body` (alias).

### `chat`

`POST /api/chat` with **`stream: false`**.

**Stdin JSON:**

```json
{
  "url": "http://localhost:11434/api/chat",
  "json": {
    "model": "llama3",
    "messages": [{"role": "user", "content": "hi"}],
    "stream": false,
    "options": {"temperature": 0.1}
  },
  "timeout": 600
}
```

Stdout: full Ollama JSON response. For streaming, use `chat-stream`.

### `chat-stream`

Same as `chat`, but forces `stream: true` and prints **one NDJSON line per token chunk** to stdout:

```json
{"content": "partial text"}
```

Empty lines and non-JSON lines from Ollama are skipped where possible.

### `generate`

`POST /api/generate` (non-streaming JSON body as documented by Ollama).

**Stdin JSON:**

```json
{
  "url": "http://localhost:11434/api/generate",
  "json": {
    "model": "my-model",
    "prompt": "...",
    "stream": false,
    "options": {"num_predict": 256}
  }
}
```

### `rerank`

`POST /api/rerank` (when supported by the server/model).

**Stdin JSON:**

```json
{
  "url": "http://localhost:11434/api/rerank",
  "json": {
    "model": "my-reranker",
    "query": "question",
    "documents": ["doc1", "doc2"],
    "top_n": 2
  }
}
```

## Error format

On failure, the CLI writes a **JSON object to stderr** (and exits with code 1), for example:

```json
{"error": "...", "status_code": 404, "body": {}}
```

The host runner maps these to application exceptions.

## Verbosity

Pass `-v` / `--verbose` before the subcommand (global flag) for minimal debug on stderr.

## Scope (out of scope)

- Starting or stopping the `ollama` OS process (`ollama serve`) — handled elsewhere in the WebUI.
- Business logic (RAG, rerank prompt parsing, Qdrant) — stays in the main repository; this CLI only performs HTTP.

## Dependency

- `requests` — the only HTTP client used inside this package.

## Version

See `pyproject.toml` (`version`).
