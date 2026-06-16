"""
Crawler domain errors — re-exported from the canonical ``error_manager`` package.

All exception classes are defined once in ``CoreModules/ErrorManager/error_manager/exceptions.py``.
This module keeps its original import path (``crawler_service.domain.errors``) working for all
existing callers.
"""

from error_manager.exceptions import CrawlError  # noqa: F401

__all__ = ["CrawlError"]
