"""
Compatibility facade for RAG system prompt loading.

Owner: ``Core/modules/prompts_manager`` (runtime store under ``WebUI/prompts/``,
bundled defaults under ``prompts_manager/bundled/``).

Call sites may keep importing ``config.rag_prompts`` until migrated to
``prompts_manager`` directly.
"""

from __future__ import annotations

from prompts_manager import (
    DEFAULT_SUFFIX,
    PROMPTS_DIR,
    RAG_SYSTEM_PREFIX,
    RAG_SYSTEM_SUFFIX,
    TRASH_DIR,
    get_rag_system_prompt,
    list_rag_prompt_names,
    load_prompt,
    rag_prompt_file_exists,
)

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
