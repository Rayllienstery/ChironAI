"""Compatibility facade for Apple Developer documentation extraction.

Implementation lives in focused modules:
- ``apple_docs_models`` for dataclasses.
- ``apple_docs_parser`` for HTML parsing and normalization.
- ``apple_docs_markdown`` for Markdown rendering.
"""

from __future__ import annotations

from webui_backend.apple_docs_html import _HAS_LXML, _extract_text, _parse_table_to_markdown, lxml_html
from webui_backend.apple_docs_markdown import _doc_scope_for_doc_kind, render_apple_doc_to_markdown
from webui_backend.apple_docs_metadata import (
    _extract_availability_from_html,
    _extract_availability_from_initial_state,
    _extract_param_names_from_swift_signature,
    _find_availability_recursive,
    _infer_macro_syntax,
    _is_macro_compiler_signature,
    _is_noise,
    _normalize_optional_func,
    _paragraph_looks_like_code,
)
from webui_backend.apple_docs_models import AppleDocBlock, AppleDocPage, AppleDocSection
from webui_backend.apple_docs_parser import build_apple_doc_page
from webui_backend.apple_docs_scope import (
    _add_scope_markers_for_strategy,
    _add_scope_markers_to_section,
    _deduplicate_by_semantic_role,
    _enhance_checklist_items,
    _extract_scope_from_h3_heading,
    _is_checklist_list_item,
    _is_ui_anchor_paragraph,
    _paragraph_mentions_different_subject,
)
from webui_backend.apple_docs_sections import (
    _deduplicate_blocks_in_section,
    _deduplicate_h3_headings,
    _reassign_controls_paragraphs_for_strategy,
    _split_long_sections_for_strategy,
    _split_mixed_lists,
)
from webui_backend.apple_docs_text import (
    BLACKLIST_PATTERNS,
    FRAMEWORK_MAP,
    _capitalize_sentence_starts,
    _clean_title,
    _is_callout_heading,
    _is_marketing_summary_paragraph,
    _is_more_info_paragraph,
    _norm_code,
    _normalize_planning_bridge,
    _normalize_stylistic_prefixes,
    _normalize_text_typos,
    _remove_more_info_sentences,
    _should_start_h3_subsection,
)

__all__ = [
    "AppleDocBlock",
    "AppleDocPage",
    "AppleDocSection",
    "BLACKLIST_PATTERNS",
    "FRAMEWORK_MAP",
    "_HAS_LXML",
    "_add_scope_markers_for_strategy",
    "_add_scope_markers_to_section",
    "_capitalize_sentence_starts",
    "_clean_title",
    "_deduplicate_blocks_in_section",
    "_deduplicate_by_semantic_role",
    "_deduplicate_h3_headings",
    "_doc_scope_for_doc_kind",
    "_enhance_checklist_items",
    "_extract_availability_from_html",
    "_extract_availability_from_initial_state",
    "_extract_param_names_from_swift_signature",
    "_extract_scope_from_h3_heading",
    "_extract_text",
    "_find_availability_recursive",
    "_infer_macro_syntax",
    "_is_callout_heading",
    "_is_checklist_list_item",
    "_is_macro_compiler_signature",
    "_is_marketing_summary_paragraph",
    "_is_more_info_paragraph",
    "_is_noise",
    "_is_ui_anchor_paragraph",
    "_norm_code",
    "_normalize_optional_func",
    "_normalize_planning_bridge",
    "_normalize_stylistic_prefixes",
    "_normalize_text_typos",
    "_paragraph_looks_like_code",
    "_paragraph_mentions_different_subject",
    "_parse_table_to_markdown",
    "_reassign_controls_paragraphs_for_strategy",
    "_remove_more_info_sentences",
    "_should_start_h3_subsection",
    "_split_long_sections_for_strategy",
    "_split_mixed_lists",
    "build_apple_doc_page",
    "lxml_html",
    "render_apple_doc_to_markdown",
]
