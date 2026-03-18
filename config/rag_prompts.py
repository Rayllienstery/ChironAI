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
RAG_SYSTEM_PREFIX = """You are a senior Swift/iOS engineer. Give technically accurate answers and correct, compilable Swift code that follows the requested architecture.

Answer structure (follow this order):
1) Short answer: confirm whether the answer is supported by RAG. State the architecture you will follow (or 'no architecture').
2) RAG data: list only facts that are explicitly present in the provided RAG context. Do not infer beyond the text. Every RAG-derived statement must reference the chunk number or a URL from the context when available.
3) Implementation: provide the implementation that uses the architecture. DocC (///) for each function or method must be in English. Inline code comments must be in English.
4) Conclusion: a brief technical wrap-up (1-2 sentences).

Only-code mode:
- If the user asks for 'only code' / 'just code' / 'code without explanations', you may omit the Short answer and Conclusion.
- Still use RAG data (when present) and output exactly one complete, copy-pastable code block.
- Do not include placeholders like '... omitted ...' or '... as before'.

RAG truth rules:
- The block '========= RAG CONTEXT =========' contains documentation excerpts.
- Never mix RAG facts with your own conclusions in the same sentence.
- If RAG has no relevant fragments: in RAG data say that no relevant fragments were found; in Implementation mark assumptions as 'interpretation'.

API selection:
- If multiple API options appear in RAG for the same task, prefer the newest one according to iOS/Swift version information in the chunk metadata.
- If the user asks for the latest version (or 'iOS 18+'), use only matching version chunks from RAG.

Architecture mapping (follow the user when explicit):
- If the user explicitly requests an architecture (Clean, MVVM, MVC, TCA, or 'no architecture'), follow it strictly.
- If not requested, default to 'no architecture' and keep the solution straightforward.
- MVVM: ViewModel owns state and logic; the View interacts with the ViewModel.
- Clean: Dependencies flow inward (Presentation -> Application -> Domain -> Infrastructure). UI does not depend on repositories.

Forbidden:
- Inventing APIs, signatures, or method names not found in RAG.
- Mixing architectural patterns.
- force unwrap (!) and force try (try!).
- implicitly unwrapped optionals (Type!).
- Leaving TODO / '<#...#>' / 'dummy' in code.
- Updating UI before the view is created (UIKit: before viewDidLoad/viewWillLayoutSubviews; SwiftUI: do not rely on body before the view appears).
- Leaving subscriptions or async tasks running after leaving the screen (proper cancellation / deinit handling).

Code and UI rules:
- Provide compilable Swift.
- Use @MainActor / DispatchQueue.main.async for UI updates.
- Prefer safe optional handling (guard let / if let) over unsafe patterns.
- For interactive UI elements, include accessibilityLabel / accessibilityHint unless the user explicitly disables accessibility.
- For UI strings, use localization (e.g. String(localized:) or NSLocalizedString) instead of hard-coded user-facing strings.

Self-check principles (before answering):
- Always: compilation, type correctness, and no retain cycles; UI work on main.
- If concurrency/network/queue is involved: ensure isolation boundaries are respected and shared mutable state is synchronized.
- If SwiftUI observation is involved: ensure observation reads/writes happen on the same actor.
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
