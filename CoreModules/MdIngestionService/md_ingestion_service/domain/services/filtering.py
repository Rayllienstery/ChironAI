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
    basename = Path(path).name

    def _matches(pat: str) -> bool:
        # Primary match against the full path.
        if fnmatch.fnmatch(path, pat) or pat in path:
            return True

        # Support common "**/..." patterns by also matching the basename.
        if "**/" in pat:
            simplified = pat.replace("**/", "")
            return (
                fnmatch.fnmatch(basename, simplified)
                or fnmatch.fnmatch(path, simplified)
                or simplified in basename
            )

        return fnmatch.fnmatch(basename, pat) or pat in basename

    for pat in rule.exclude_patterns:
        if _matches(pat):
            return False
    if rule.include_patterns and not any(_matches(p) for p in rule.include_patterns):
        return False
    if rule.min_size_chars > 0 and len(file.content) < rule.min_size_chars:
        return False
    return not (rule.max_size_chars > 0 and len(file.content) > rule.max_size_chars)


def default_filter_rule() -> FilterRule:
    """Default rule: all .md files, no exclusions."""
    return FilterRule(include_patterns=["**/*.md"], exclude_patterns=[], min_size_chars=0, max_size_chars=0)


__all__ = ["apply_filter", "default_filter_rule"]
