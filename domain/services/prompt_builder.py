"""Compat wrapper re-exporting canonical ``rag_service.domain.services.prompt_builder``."""

from rag_service.domain.services import prompt_builder as _canonical_prompt_builder
from rag_service.domain.services.prompt_builder import *  # noqa: F401,F403

__all__ = list(_canonical_prompt_builder.__all__)
