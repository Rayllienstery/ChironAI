"""Compat wrapper re-exporting canonical ``rag_service.domain.services.rag_trigger``."""

from rag_service.domain.services import rag_trigger as _canonical_rag_trigger
from rag_service.domain.services.rag_trigger import *  # noqa: F401,F403

__all__ = list(_canonical_rag_trigger.__all__)
