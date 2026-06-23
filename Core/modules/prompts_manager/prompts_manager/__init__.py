"""Host-owned RAG prompt template storage and loading."""

from __future__ import annotations

from prompts_manager.defaults import DEFAULT_SUFFIX, RAG_SYSTEM_PREFIX, RAG_SYSTEM_SUFFIX
from prompts_manager.paths import resolve_prompts_dir, trash_dir
from prompts_manager.storage import (
    get_rag_system_prompt,
    list_rag_prompt_names,
    load_prompt,
    rag_prompt_file_exists,
)

PROMPTS_DIR = resolve_prompts_dir()
TRASH_DIR = trash_dir()

__all__ = [
    "DEFAULT_SUFFIX",
    "PROMPTS_DIR",
    "RAG_SYSTEM_PREFIX",
    "RAG_SYSTEM_SUFFIX",
    "TRASH_DIR",
    "get_rag_system_prompt",
    "list_rag_prompt_names",
    "load_prompt",
    "rag_prompt_file_exists",
]
