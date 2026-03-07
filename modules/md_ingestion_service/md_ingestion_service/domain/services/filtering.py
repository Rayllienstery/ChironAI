"""
Filter documents by path patterns and size.
"""

from __future__ import annotations

import fnmatch
from pathlib import Path

from md_ingestion_service.domain.entities import FilterRule, MarkdownFile


def apply_filter(file: MarkdownFile, rule: FilterRule) -> bool:
    """True if file passes the filter (include patterns, exclude patterns, size)."""
    path = file.path or file.filename
    for pat in rule.exclude_patterns:
        if fnmatch.fnmatch(path, pat) or pat in path:
            return False
    if rule.include_patterns:
        if not any(fnmatch.fnmatch(path, p) or p in path for p in rule.include_patterns):
            return False
    if rule.min_size_chars > 0 and len(file.content) < rule.min_size_chars:
        return False
    if rule.max_size_chars > 0 and len(file.content) > rule.max_size_chars:
        return False
    return True


def default_filter_rule() -> FilterRule:
    """Default rule: all .md files, no exclusions."""
    return FilterRule(include_patterns=["**/*.md"], exclude_patterns=[], min_size_chars=0, max_size_chars=0)


__all__ = ["apply_filter", "default_filter_rule"]
