"""Compat wrapper re-exporting canonical ``rag_service.domain.services.rag_trace``."""

from rag_service.domain.services import rag_trace as _canonical_rag_trace
from rag_service.domain.services.rag_trace import *  # noqa: F401,F403

__all__ = list(_canonical_rag_trace.__all__)
