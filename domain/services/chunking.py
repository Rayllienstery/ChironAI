"""Compat wrapper for canonical ``rag_service.domain.services.chunking``."""

from rag_service.domain.services import chunking as _canonical_chunking
from rag_service.domain.services.chunking import *  # noqa: F401,F403
from rag_service.domain.services.chunking import _is_heading_only_chunk  # noqa: F401

__all__ = list(_canonical_chunking.__all__) + ["_is_heading_only_chunk"]
