"""Load and enumerate RAG system prompt templates."""

from __future__ import annotations

from pathlib import Path

from prompts_manager.defaults import DEFAULT_SUFFIX, RAG_SYSTEM_PREFIX, RAG_SYSTEM_SUFFIX
from prompts_manager.paths import bundled_prompts_dir, resolve_prompts_dir, runtime_prompts_dir


def _is_safe_prompt_name(name: str) -> bool:
    return bool(name) and ".." not in name and "/" not in name and "\\" not in name


def _prompt_names_in_dir(directory: Path) -> list[str]:
    if not directory.is_dir():
        return []
    names: list[str] = []
    for path in directory.iterdir():
        if path.suffix.lower() == ".md" and path.name[0] != ".":
            names.append(path.stem)
    return names


def _resolve_prompt_path(name: str) -> Path | None:
    if not _is_safe_prompt_name(name):
        return None
    runtime_path = runtime_prompts_dir() / f"{name}.md"
    if runtime_path.is_file():
        return runtime_path
    bundled_path = bundled_prompts_dir() / f"{name}.md"
    if bundled_path.is_file():
        return bundled_path
    return None


def list_rag_prompt_names() -> list[str]:
    """Return sorted prompt names from runtime storage and bundled defaults."""
    resolve_prompts_dir()
    names = set(_prompt_names_in_dir(runtime_prompts_dir()))
    names.update(_prompt_names_in_dir(bundled_prompts_dir()))
    return sorted(names)


def resolve_prompt_file(name: str) -> Path | None:
    """Return the runtime or bundled template path for ``name``."""
    resolve_prompts_dir()
    return _resolve_prompt_path(name)


def read_prompt_content(name: str) -> str | None:
    """Return template text when a runtime or bundled prompt exists."""
    path = resolve_prompt_file(name)
    if path is None:
        return None
    return path.read_text(encoding="utf-8")


def load_prompt(name: str) -> tuple[str, str]:
    """
    Load (prefix, suffix) for the given prompt name (filename stem).
    Falls back to built-in defaults when the template is missing or unreadable.
    """
    path = _resolve_prompt_path(name)
    if path is None:
        return RAG_SYSTEM_PREFIX, RAG_SYSTEM_SUFFIX
    try:
        text = path.read_text(encoding="utf-8")
        prefix = text.strip()
        if not prefix:
            return RAG_SYSTEM_PREFIX, RAG_SYSTEM_SUFFIX
        return prefix + "\n", DEFAULT_SUFFIX
    except Exception:
        return RAG_SYSTEM_PREFIX, RAG_SYSTEM_SUFFIX


def rag_prompt_file_exists(name: str) -> bool:
    """True when a runtime or bundled template exists for ``name``."""
    resolve_prompts_dir()
    return _resolve_prompt_path(name) is not None


def get_rag_system_prompt(prompt_name: str | None = None) -> tuple[str, str]:
    """
    Return (system_prefix, system_suffix) for RAG.
    When ``prompt_name`` is None, use config (``rag.prompt``) or env ``RAG_PROMPT``.
    """
    if prompt_name is None:
        try:
            from config import get_rag_prompt_name

            prompt_name = get_rag_prompt_name()
        except Exception:
            prompt_name = "system_rag_v1"
    return load_prompt(prompt_name)


__all__ = [
    "get_rag_system_prompt",
    "list_rag_prompt_names",
    "load_prompt",
    "rag_prompt_file_exists",
    "read_prompt_content",
    "resolve_prompt_file",
]
