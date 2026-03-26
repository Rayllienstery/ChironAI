"""
RAG system prompt: load from Markdown files in prompts/ and switch by name.

Prompts are stored as prompts/<name>.md (e.g. prompts/system_rag_v1.md).
Name = filename without extension. Default name from config (rag.prompt) or env RAG_PROMPT.

Used by rag_proxy (HTTP), rag_client (CLI), and api/http/rag_routes.
"""

from __future__ import annotations

import os
from pathlib import Path

# Project root (parent of config/)
_CONFIG_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _CONFIG_DIR.parent
PROMPTS_DIR = _PROJECT_ROOT / "prompts"

# Default suffix appended after system prompt (RAG context block follows)
DEFAULT_SUFFIX = "\n=================================\n"

# Fallback when no prompts dir or file missing (e.g. tests)
RAG_SYSTEM_PREFIX = """You are a helpful assistant.

When tool-call mode is enabled by the client/proxy:
- Follow the tool instructions exactly.
- Return machine-readable output only (no prose, no markdown, no code fences).
- If asked to call a tool, output ONLY a single valid JSON object for that tool.

When tool-call mode is NOT enabled:
- Answer normally and concisely.

- Built-in tools (`browser.search`, `browser.open`, `browser.find`, `python`) are treated separately from non-builtin tools.
- Non-builtin tools must be called via `functions.<tool_name>` and routed to the `commentary` channel.
- Keep tool call arguments as valid JSON and do not add free text around JSON payloads.
- Do not degrade tool-use behavior by removing or simplifying tool schema rendering in the template.

Recommended blocks for Template Editor (keep syntax unchanged):

```gotemplate
{{- $hasNonBuiltinTools := false }}
{{- if .Tools -}}
{{- $hasBrowserSearch := false }}
{{- $hasBrowserOpen := false }}
{{- $hasBrowserFind := false }}
{{- $hasPython := false }}
  {{- range .Tools }}
    {{- if eq .Function.Name "browser.search" -}}{{- $hasBrowserSearch = true -}}
    {{- else if eq .Function.Name "browser.open" -}}{{- $hasBrowserOpen = true -}}
    {{- else if eq .Function.Name "browser.find" -}}{{- $hasBrowserFind = true -}}
    {{- else if eq .Function.Name "python" -}}{{- $hasPython = true -}}
    {{- else }}{{ $hasNonBuiltinTools = true -}}
    {{- end }}
  {{- end }}
{{- end }}
```

```gotemplate
{{- if $hasNonBuiltinTools }}
# Tools

## functions
namespace functions {
{{- range .Tools }}
{{- if not (or (eq .Function.Name "browser.search") (eq .Function.Name "browser.open") (eq .Function.Name "browser.find") (eq .Function.Name "python")) }}
{{if .Function.Description }}
// {{ .Function.Description }}
{{- end }}
{{- if and .Function.Parameters.Properties (gt (len .Function.Parameters.Properties) 0) }}
type {{ .Function.Name }} = (_: {
{{- range $name, $prop := .Function.Parameters.Properties }}
  {{ $name }}: {{ $prop | toTypeScriptType }},
{{- end }}
}) => any;
{{- else }}
type {{ .Function.Name }} = () => any;
{{- end }}
{{- end }}
{{- end }}
} // namespace functions
{{- end }}
```

```gotemplate
{{- if gt (len $msg.ToolCalls) 0 -}}
  {{- range $j, $toolCall := $msg.ToolCalls -}}
    {{- $isBuiltin := or (eq $toolCall.Function.Name "python") (eq $toolCall.Function.Name "browser.search") (eq $toolCall.Function.Name "browser.open") (eq $toolCall.Function.Name "browser.find") -}}
    <|start|>assistant<|channel|>{{ if $isBuiltin }}analysis{{ else }}commentary{{ end }} to={{ if not $isBuiltin}}functions.{{end}}{{ $toolCall.Function.Name }} <|constrain|>json<|message|>{{ $toolCall.Function.Arguments }}<|call|>
  {{- end -}}
{{- end -}}
```
"""

RAG_SYSTEM_SUFFIX = DEFAULT_SUFFIX


def list_rag_prompt_names() -> list[str]:
    """Return sorted list of prompt names (stems of prompts/*.md)."""
    if not PROMPTS_DIR.is_dir():
        return []
    names: list[str] = []
    for path in PROMPTS_DIR.iterdir():
        if path.suffix.lower() == ".md" and path.name[0] != ".":
            names.append(path.stem)
    return sorted(names)


def load_prompt(name: str) -> tuple[str, str]:
    """
    Load (prefix, suffix) for the given prompt name (filename stem).
    File = prompts/<name>.md. Content = prefix; suffix = DEFAULT_SUFFIX.
    If file missing or unreadable, returns built-in RAG_SYSTEM_PREFIX, RAG_SYSTEM_SUFFIX.
    """
    if not name or ".." in name or "/" in name or "\\" in name:
        return RAG_SYSTEM_PREFIX, RAG_SYSTEM_SUFFIX
    path = PROMPTS_DIR / f"{name}.md"
    if not path.is_file():
        return RAG_SYSTEM_PREFIX, RAG_SYSTEM_SUFFIX
    try:
        text = path.read_text(encoding="utf-8")
        prefix = text.strip()
        if not prefix:
            return RAG_SYSTEM_PREFIX, RAG_SYSTEM_SUFFIX
        return prefix + "\n", DEFAULT_SUFFIX
    except Exception:
        return RAG_SYSTEM_PREFIX, RAG_SYSTEM_SUFFIX


def get_rag_system_prompt(prompt_name: str | None = None) -> tuple[str, str]:
    """
    Return (system_prefix, system_suffix) for RAG.
    If prompt_name is None, use config (rag.prompt) or env RAG_PROMPT.
    Switching by name: pass the stem of a file in prompts/*.md (e.g. "system_rag_v1").
    """
    if prompt_name is None:
        try:
            from config import get_rag_prompt_name
            prompt_name = get_rag_prompt_name()
        except Exception:
            prompt_name = "system_rag_v1"
    return load_prompt(prompt_name)


def get_rag_system_prompt_swift_mode(
    prompt_name: str | None = None,
    swift_mode: str | None = None,
) -> tuple[str, str]:
    """
    Return (system_prefix, system_suffix) for RAG with Swift 5/6 mode support.
    
    Args:
        prompt_name: Name of prompt file (stem of prompts/*.md). If None, uses config default.
        swift_mode: "swift5", "swift6", or None/"default" for default behavior.
    
    Returns:
        (prefix, suffix) tuple with Swift mode-specific modifications.
    """
    prefix, suffix = get_rag_system_prompt(prompt_name)
    
    if swift_mode in ("swift5", "swift6"):
        # Add Swift version-specific instruction at the beginning
        swift_header = "\n---------- SWIFT VERSION MODE ----------\n"
        if swift_mode == "swift5":
            swift_header += (
                "Target version: Swift 5.x. "
                "Use Swift 5 rules: no strict compiler concurrency checking, "
                "you may use ObservableObject/@Published for SwiftUI, "
                "and there is no mandatory Sendable requirement across isolation boundaries. "
                "Principles 6-11 (strict Swift 6 concurrency) apply only if Swift 6 is explicitly requested.\n"
            )
        elif swift_mode == "swift6":
            swift_header += (
                "Target version: Swift 6.0+. "
                "Always follow strict concurrency (principles 6-11): "
                "Sendable across isolation boundaries, @Observable for SwiftUI (not ObservableObject), "
                "all @Observable changes on MainActor, "
                "and UIKit + @Observable requires UIObservationTrackingEnabled and MainActor for all changes. "
                "Principles 6-11 apply ALWAYS for Swift 6.\n"
            )
        prefix = swift_header + prefix
    # For "default" or None, return as-is (prompt already contains both Swift 5 and 6 guidance)
    
    return prefix, suffix


__all__ = [
    "PROMPTS_DIR",
    "DEFAULT_SUFFIX",
    "RAG_SYSTEM_PREFIX",
    "RAG_SYSTEM_SUFFIX",
    "list_rag_prompt_names",
    "load_prompt",
    "get_rag_system_prompt",
    "get_rag_system_prompt_swift_mode",
]
