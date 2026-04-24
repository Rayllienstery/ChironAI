"""Compat wrapper re-exporting canonical ``rag_service.domain.services.rerank``."""

from rag_service.domain.services import rerank as _canonical_rerank
from rag_service.domain.services.rerank import *  # noqa: F401,F403

__all__ = list(_canonical_rerank.__all__)
