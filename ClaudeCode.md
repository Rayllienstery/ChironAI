# Claude Code Integration Plan

> Implementation reference for adding Claude Code CLI support to ChironAI LLM Proxy.
> Written as a step-by-step technical guide to be followed during implementation.

---

## Current State — What Already Exists

The Anthropic compat layer is **fully built**. Almost nothing needs to be added to the proxy itself.

| Component | Status | Location |
|-----------|--------|----------|
| `POST /v1/messages` endpoint | ✅ Done | `v1_blueprint.py:890` |
| Anthropic request → OpenAI body conversion | ✅ Done | `anthropic_compat.anthropic_messages_request_to_openai_body` |
| OpenAI response → Anthropic message conversion | ✅ Done | `anthropic_compat.openai_chat_completion_to_anthropic_message` |
| Anthropic SSE from OpenAI SSE stream | ✅ Done | `anthropic_compat.iter_anthropic_sse_from_openai_sse_lines` |
| `tool_use` / `tool_result` blocks | ✅ Done | `anthropic_compat._flatten_anthropic_messages_to_openai` |
| `GET /v1/models` Anthropic format | ✅ Done | `v1_blueprint.py:850` — detects `anthropic-version` header |
| Proxy API key auth | ✅ Done | `verify_proxy_api_key` — used by all v1 routes |

**What this means:** Claude Code can technically connect *right now* by pointing
`ANTHROPIC_BASE_URL=http://127.0.0.1:8080/v1` at the proxy and setting `ANTHROPIC_API_KEY`
to the ChironAI proxy key. The missing piece is the **launcher** — automate that setup
the same way Codex was automated.

---

## What Claude Code Actually Needs at Runtime

```
CLAUDE_CONFIG_DIR    = ~/.chironai/claude/        ← isolated from ~/.claude/ (CODEX_HOME equivalent)
ANTHROPIC_BASE_URL   = http://127.0.0.1:8080/v1   ← ChironAI proxy
ANTHROPIC_API_KEY    = chiron_sk_...               ← proxy key
ANTHROPIC_AUTH_TOKEN = chiron_sk_...               ← same key; older Claude versions use this field
```

`CLAUDE_CONFIG_DIR` is the exact equivalent of `CODEX_HOME`. It redirects all of Claude Code's
state files (conversation history, project settings, auth) to a separate directory, keeping
`~/.claude/` untouched for the user's real Claude sessions.
Source: Ollama's `ollama launch claude` implementation (https://docs.ollama.com/integrations/claude-code).

`ANTHROPIC_AUTH_TOKEN` vs `ANTHROPIC_API_KEY` — different Claude Code versions check one or the
other. Always set both to the proxy key to cover all versions.

No config file to write (unlike Codex's `config.toml`). Pure env vars at launch time.

## Claude Code Installation

Claude Code is **not an npm package** — it moved to a native binary installer.

```powershell
# Windows
irm https://claude.ai/install.ps1 | iex
```

```bash
# macOS / Linux
curl -fsSL https://claude.ai/install.sh | bash
```

The native installer puts `claude.exe` directly in a user-local PATH directory — no `.cmd`
wrapper, no npm complications. Detection: `shutil.which("claude")` works on all platforms.
Still apply the `.chironai/bin/` skip guard for safety.

Update the `Getting Started` step 1 install instruction in `provider.py` accordingly:
`"Install via: irm https://claude.ai/install.ps1 | iex"` (Windows), not npm.

---

## Implementation Steps

### Step 1 — `application/claude_launcher.py`

Mirror the structure of `application/codex_launcher.py`. Key functions:

#### `_find_claude_path() -> str`
- Unlike Codex, Claude Code is a **native binary** (not npm), so no `.cmd` wrapper lookup needed
- Primary: `shutil.which("claude")` — native installer puts it in PATH automatically
- Skip any path under `.chironai/bin/` (PATH shadowing guard, same as Codex)
- On Windows: also check `shutil.which("claude.cmd")` as fallback, just in case
- If not found: return `None` (caller raises `ClaudeLauncherError`)

#### `claude_status() -> dict`
- Use `_find_claude_path()`
- Run `claude --version` with `shell=True` on Windows (same WinError 2 issue)
- Check output doesn't contain "chironai" (shadowing guard)
- Returns `{"installed": bool, "path": str, "version": str, "error": str}`

#### `build_claude_env(api_key: str) -> dict`
```python
env = os.environ.copy()
env["CLAUDE_CONFIG_DIR"] = str(claude_home())          # isolated state dir
env["ANTHROPIC_BASE_URL"] = f"http://127.0.0.1:{get_server_port()}/v1"
env["ANTHROPIC_API_KEY"] = api_key
env["ANTHROPIC_AUTH_TOKEN"] = api_key                  # older Claude versions use this
return env
```

#### `build_claude_argv(extra_args: list[str] | None = None) -> list[str]`
```python
claude_path = _find_claude_path() or "claude"
return [claude_path, *(extra_args or [])]
```
No `--model` flag — Claude Code uses the model configured in its own session UI
or via `--model` passed by user. The build selection happens in ChironAI proxy
(which build routes the request).

#### `claude_home() -> Path`
```python
CHIRONAI_CLAUDE_HOME = Path.home() / ".chironai" / "claude"

def claude_home() -> Path:
    return CHIRONAI_CLAUDE_HOME
```

#### `require_claude_installed() -> None`
Same pattern as `require_codex_installed()`. Error message:
```
Windows: "Claude Code is not installed. Install with: irm https://claude.ai/install.ps1 | iex"
macOS/Linux: "Claude Code is not installed. Install with: curl -fsSL https://claude.ai/install.sh | bash"
```
Use `sys.platform` to pick the right message.

#### `build_command_preview() -> str`
```python
return "chironai claude"
```

#### `write_claude_profile(base_url: str, *, build: dict | None = None) -> Path`
Writes `~/.chironai/claude/config.json` — inside `CLAUDE_CONFIG_DIR`, NOT `~/.claude/`.
This is the Claude equivalent of Codex's `write_codex_profile` / `config.toml`.

```python
def write_claude_profile(base_url: str, *, build: dict | None = None) -> Path:
    home = claude_home()
    home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.json"
    data: dict = {"apiBaseUrl": base_url}
    if build:
        ctx = build.get("num_ctx")
        if ctx:
            data["contextWindowSize"] = int(ctx)
    config_path.write_text(json.dumps(data, indent=2))
    return config_path
```

The launcher always creates the `~/.chironai/claude/` directory before launching,
so Claude Code writes its session state there instead of `~/.claude/`.
Because `CLAUDE_CONFIG_DIR` is set at runtime, the config.json is optional/supplemental
but useful for persisting model metadata hints.

---

### Step 2 — `api/cli/__main__.py` — Add `chironai claude` command

#### Add `cmd_claude(ns)` function

```python
def cmd_claude(ns: argparse.Namespace) -> int:
    # same boilerplate as cmd_codex: import from application.claude_launcher
    try:
        from application.claude_launcher import (
            ClaudeLauncherError,
            build_claude_argv,
            build_claude_env,
            require_claude_installed,
            reveal_existing_proxy_key,   # reuse from codex_launcher
        )
        from config import get_server_port
        from infrastructure.database import get_settings_repository
    except ImportError as e:
        print(str(e), file=sys.stderr)
        return 1

    try:
        require_claude_installed()
        settings_repo = get_settings_repository()
        api_key = reveal_existing_proxy_key(settings_repo)  # same function, same key
        extra_args = _strip_dashdash(list(getattr(ns, "extra_args", None) or []))
        argv = build_claude_argv(extra_args)
        env = build_claude_env(api_key)
        print(f"ANTHROPIC_BASE_URL={env['ANTHROPIC_BASE_URL']}")
        print(f"Command: chironai claude")
        if bool(getattr(ns, "config", False)):
            return 0
        return subprocess.run(argv, cwd=os.getcwd(), env=env).returncode
    except ClaudeLauncherError as e:
        print(str(e), file=sys.stderr)
        return 1
```

#### Register subparser

```python
p_claude = sub.add_parser("claude", help="Launch Claude Code with ChironAI LLM Proxy")
p_claude.add_argument("--config", action="store_true", help="Print config without launching")
p_claude.add_argument("extra_args", nargs=argparse.REMAINDER, help="Arguments passed to claude")
p_claude.set_defaults(_run=cmd_claude)
```

---

### Step 3 — `extensions/bundled/claude-launcher/`

Structure mirrors `extensions/bundled/codex-launcher/`.

#### `chironai-extension.json`
```json
{
  "id": "claude-launcher",
  "version": "0.1.0",
  "api_version": "1",
  "type": "ui_extension",
  "title": "Claude Code",
  "description": "Configure and launch Claude Code against ChironAI LLM Proxy IDE builds.",
  "icon": "icons/claude-light.svg",
  "tab_ui": {
    "id": "claude",
    "title": "Claude Code",
    "icon": "icons/claude-light.svg",
    "order": 56
  },
  "backend": {
    "entrypoint": "backend.provider:create_provider"
  },
  "capabilities": {
    "tab_ui": true,
    "service_actions": true
  },
  "compatibility": {
    "app": "chironai",
    "extension_api_version": "1"
  },
  "metadata": {
    "service": "claude-launcher"
  }
}
```

#### `backend/provider.py`

Mirrors `codex-launcher/backend/provider.py`. Key differences:
- No `write_codex_profile` equivalent needed in `configure_claude` action —
  just validate proxy is reachable and key is configured, then return the env vars
- `_diagnostics()`: call `claude_status()` instead of `codex_status()`
- No `ide_builds` filtering — Claude Code doesn't need `ide_mode` flag because it
  connects to the proxy directly (any build is accessible via model selector inside Claude)
- `setup_steps` in payload:
  1. Install Claude Code CLI → Windows: `irm https://claude.ai/install.ps1 | iex` / Linux/Mac: `curl -fsSL https://claude.ai/install.sh | bash`
  2. Configure API key → same as Codex step
  3. Proxy reachable → same check
  4. Launch → `chironai claude`
- Actions: `refresh`, `copy_command`
  - No `configure_claude` action needed (config written automatically inside `~/.chironai/claude/`)

#### `icons/claude-light.svg`

Use Anthropic's Claude icon or a simple SVG. Can start with a placeholder letter "C"
and replace later. Must be a single-color SVG for the tab icon system.

---

### Step 4 — `extensions/registry/extensions.json`

Add the new extension entry. Same pattern as `codex-launcher`.

---

## Known Gotchas and Gaps to Fix

### 4.1 — `tool_result` missing `name` field (same bug as Codex)

In `anthropic_compat._flatten_anthropic_messages_to_openai`, when converting
`tool_result` blocks from user turns to OpenAI `role: "tool"` messages:

```python
out.append(
    {"role": "tool", "tool_call_id": str(tid), "content": tr_content}
)
```

**The `name` field is NOT set.** `tid` is `tool_use_id` — the same as `call_id` in
the preceding assistant `tool_use` block. The name recovery in
`_preflight_native_tool_messages` handles this via `tool_call_id_to_name` map built from
assistant messages — but only if the assistant message with `tool_use` is present
in the same conversation turn.

**Verification needed:** Test a multi-turn Claude Code session with tool use and check
if `function_response.name: Name cannot be empty` reappears. The fix from
`v1_blueprint.py` (for Codex's `function_call` items) does NOT help here because
Claude Code uses the standard Anthropic Messages format, not Responses API.

**If bug occurs:** In `_flatten_anthropic_messages_to_openai`, when emitting `tool_result`
messages, also add `"name"` by looking up the `tool_use` id in preceding assistant messages.
Add a pre-pass to build `tool_use_id → name` map before the main loop.

### 4.2 — Extended Thinking (`thinking` blocks)

Claude Code can request extended thinking via `"thinking": {"type": "enabled", "budget_tokens": N}`.
The proxy currently ignores this field (it's not passed through to Ollama).

Ollama/Gemini does support thinking via separate mechanisms (`chat_think` in ChironAI builds).
The thinking request from Claude Code will be silently dropped — not an error, just no thinking.
This is acceptable for now. If needed later: detect `thinking.enabled` in request body
and set `chat_think = True` equivalent in the Ollama options overlay.

Also: Claude Code may return `thinking` content blocks in responses. The current
`openai_chat_completion_to_anthropic_message` only handles `text` and `tool_use` blocks.
This is fine as long as we're going Ollama → proxy → Claude Code (Ollama doesn't emit
thinking blocks in the way Claude does natively).

### 4.3 — `anthropic-beta` headers

Claude Code sends beta headers like:
```
anthropic-beta: computer-use-2024-10-22
anthropic-beta: interleaved-thinking-2025-05-14
```

The proxy's `v1/messages` endpoint currently doesn't read or forward these headers.
For the use case of Claude Code → ChironAI → Ollama, these headers are irrelevant
(Ollama doesn't support these betas). No action needed unless directly proxying to Anthropic.

**However:** Some Claude Code versions refuse to connect if the server doesn't echo back
certain beta capabilities. If connection fails with a beta-related error:
1. In `anthropic_messages()` endpoint, add the beta headers to the response.
2. Or return a `204` stub from `GET /v1/betas` if Claude Code polls that.

### 4.4 — Windows PATH shadowing

ChironAI may install a `claude.cmd` wrapper in `~/.chironai/bin/` in the future (same as
the old `codex.cmd` that was deleted). The `_find_claude_path()` function must skip
`.chironai/bin/` paths, same pattern as `_find_openai_codex_path()`.

### 4.5 — No `ide_mode` filter for Claude Code

Unlike Codex (which filters builds via `ide_mode`), Claude Code should expose ALL builds
in the proxy, because Claude Code's model selector inside the TUI lets the user pick
the model (= build ID). Builds are already listed in `GET /v1/models`.

If build filtering is desired in the future: add `claude_mode` field to builds,
parallel to `ide_mode`. For now, no filter.

### 4.6 — Model name in Claude Code

Claude Code will show the model as whatever `GET /v1/models` returns (the build IDs).
The user will see "gemini", "gpt4o", etc. — the ChironAI build names. This is expected.

If a build ID contains characters not allowed by Anthropic's model validator, Claude Code
may reject it. Allowed: alphanumeric, `-`, `.`, `/`, `_`. Verify build IDs comply.

### 4.7 — Streaming multi-tool-call turns

`iter_anthropic_sse_from_openai_sse_lines` currently handles **one tool call at a time**
per SSE stream. If the proxy emits multiple `tool_calls` in one response (e.g. parallel
tool use), only the first is processed correctly.

Claude Code typically sends one tool per turn, but `Write` + `Bash` in the same turn is
possible. Fix if needed: iterate over all `tcs` in the delta, track multiple open
`tool_block_open` states keyed by index.

---

## Testing Checklist

### Smoke test (no code changes needed — test existing compat layer first)
```powershell
# Windows PowerShell
$env:CLAUDE_CONFIG_DIR   = "$HOME\.chironai\claude"
$env:ANTHROPIC_BASE_URL  = "http://127.0.0.1:8080/v1"
$env:ANTHROPIC_API_KEY   = "chiron_sk_..."
$env:ANTHROPIC_AUTH_TOKEN = "chiron_sk_..."
claude "Hello, what files are in this directory?"
```
```bash
# macOS / Linux
CLAUDE_CONFIG_DIR=~/.chironai/claude \
  ANTHROPIC_BASE_URL=http://127.0.0.1:8080/v1 \
  ANTHROPIC_API_KEY=chiron_sk_... \
  ANTHROPIC_AUTH_TOKEN=chiron_sk_... \
  claude "Hello, what files are in this directory?"
```
If this works → the `/v1/messages` endpoint and Anthropic compat are already solid.
Also verifies `CLAUDE_CONFIG_DIR` isolation — check that `~/.claude/` was NOT touched.

### Test tool use
```bash
claude "Read the file README.md and summarize it"
```
This triggers a `Read` tool call → `tool_use` block in response → Claude sends
`tool_result` back → second turn. Verify no `function_response.name` errors in logs.

### Test streaming
```bash
claude --no-stream "Explain the architecture of this project"
# Then:
claude "Explain the architecture of this project"
```
Both should work. Non-streaming uses `openai_chat_completion_to_anthropic_message`.
Streaming uses `iter_anthropic_sse_from_openai_sse_lines`.

### Test `chironai claude` CLI
```bash
chironai claude "Find all TODO comments in the codebase"
```
Should launch Claude Code with correct env vars and proxy URL.

### Test extension tab
- Install `claude-launcher` extension
- Codex tab shows "Getting Started" steps
- Step 1 (Install) green if `claude --version` works
- Step 3 (Proxy reachable) green
- Step 4 (Launch) shows `chironai claude`

---

## Implementation Order

1. **Smoke test first** — run Claude Code manually with env vars pointing at proxy.
   If it works cleanly (no tool use errors), the compat layer is solid.
2. **`application/claude_launcher.py`** — ~100 lines, very similar to codex_launcher.
3. **`api/cli/__main__.py`** — add `cmd_claude` and subparser (~40 lines).
4. **Fix tool_result name bug if smoke test reveals it** (see §4.1).
5. **Extension tab** — copy codex-launcher, adapt for Claude (simpler since no build filter).
6. **Register in `extensions/registry/extensions.json`**.
7. **Test full flow** with the checklist above.

Total estimated effort: **1 day** for steps 1-4, half day for steps 5-7.
