"""
RAG retrieval helpers for the ``rag_service`` package.

Canonical implementation: ``domain.services.retrieval``. Re-exported for backward
compatibility (tests, ``rag_service.infrastructure`` imports).
"""

from __future__ import annotations

from domain.services import retrieval as _canonical

__all__ = list(_canonical.__all__)

_globals = globals()
for _name in _canonical.__all__:
    _globals[_name] = getattr(_canonical, _name)
del _globals, _name, _canonical
