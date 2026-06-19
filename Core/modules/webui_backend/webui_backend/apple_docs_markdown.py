"""Markdown rendering for extracted Apple Developer documentation pages."""

from __future__ import annotations

import re

from webui_backend.apple_docs_metadata import (
    _infer_macro_syntax,
    _is_macro_compiler_signature,
    _paragraph_looks_like_code,
)
from webui_backend.apple_docs_models import AppleDocPage
from webui_backend.apple_docs_text import (
    _capitalize_sentence_starts,
    _is_callout_heading,
    _is_marketing_summary_paragraph,
    _is_more_info_paragraph,
    _normalize_planning_bridge,
    _normalize_stylistic_prefixes,
    _normalize_text_typos,
    _remove_more_info_sentences,
)


def _doc_scope_for_doc_kind(doc_kind: str | None) -> str:
    kind = (doc_kind or "").strip().lower()
    if kind in {"api_ref", "api_ref_macro"}:
        return "api_symbol"
    if kind in {"conceptual", "conceptual_strategy", "overview"}:
        return "guide"
    return ""


def render_apple_doc_to_markdown(page: AppleDocPage) -> str:
    """
    Render `AppleDocPage` into RAG-optimized markdown.

    Goals:
    - Clear H1 title and H2/H3 section headings.
    - Short paragraphs and list items (no huge code fences wrapping everything).
    - Fenced code blocks with explicit language (e.g. ```swift).
    - Compact metadata block at the top to aid filtering, but lightweight
      enough to not pollute semantic content.
    """
    lines: list[str] = []

    # Lightweight metadata comment block in YAML-like format for easy parsing.
    # This format ensures availability metadata never pollutes embeddings while
    # remaining accessible for post-retrieval filtering and version checks.
    lines.append("<!--")
    lines.append("meta:")
    lines.append(f"  url: {page.url}")
    if page.framework:
        lines.append(f"  framework: {page.framework}")
    if page.doc_kind:
        lines.append(f"  doc_kind: {page.doc_kind}")
    doc_scope = _doc_scope_for_doc_kind(page.doc_kind)
    if doc_scope:
        lines.append(f"  doc_scope: {doc_scope}")
    if page.platforms:
        lines.append(f"  platforms: {', '.join(page.platforms)}")
    if page.availability:
        lines.append("  availability:")
        # Sort platforms for consistent output (iOS, macOS, etc. first, then Swift)
        sorted_items = sorted(page.availability.items(), key=lambda x: (x[0] != "Swift", x[0]))
        for platform, version in sorted_items:
            lines.append(f"    {platform}: {version}")
    lines.append("-->")
    lines.append("")

    # Title as H1.
    lines.append(f"# {page.title}")
    lines.append("")

    # Optional subtitle as short paragraph under title.
    if page.subtitle:
        lines.append(page.subtitle)
        lines.append("")

    # For macro API-reference pages, render a dedicated Syntax section
    # with the user-facing macro annotation (e.g. "@Model") before any
    # other sections. We deliberately hide compiler-level macro
    # signatures from the main flow.
    if page.doc_kind == "api_ref_macro":
        syntax_line = _infer_macro_syntax(page)
        if syntax_line:
            lines.append("## Syntax")
            lines.append("")
            lines.append("```swift")
            lines.append(syntax_line)
            lines.append("```")
            lines.append("")

    in_list = False
    # For certain conceptual strategy documents, we want to avoid inlining large
    # reference tables in the middle of the prose. Instead, we collect them and
    # render them at the end under a dedicated reference section so that the
    # main narrative remains cleaner for RAG.
    strategy_tables: list[str] = []

    for section_index, section in enumerate(page.sections):
        # Skip empty sections (no blocks) — they create bad chunks for RAG.
        # Exception: H2 sections that are parents of H3 subsections should render
        # even if empty, as they provide important structural hierarchy.
        is_parent_h2 = (
            section.level == 2 
            and section.heading 
            and section_index + 1 < len(page.sections)
            and page.sections[section_index + 1].level == 3
        )
        if not section.blocks and not is_parent_h2:
            continue
        is_callout = section.heading and _is_callout_heading(section.heading)
        callout_first_body = bool(is_callout)

        if section.heading:
            # For macro API-ref pages, normalize certain headings.
            heading_text = section.heading
            if page.doc_kind == "api_ref_macro" and heading_text in {"Mentioned in", "Mentioned In"}:
                heading_text = "Usage"

            # Check if this is a callout heading (Tip, Important, etc.).
            if is_callout:
                # Render as markdown callout block for better semantic signal.
                callout_type = heading_text.strip()
                lines.append(f"> **{callout_type}**")
            else:
                # Regular section heading: H1 already used for page title; bump to >= H2.
                level = max(section.level, 2)
                level = min(level, 6)
                lines.append("#" * level + f" {heading_text}")
                lines.append("")

        for block in section.blocks:
            if block.kind == "paragraph":
                # Emit paragraphs that look like code as fenced code blocks (RAG best practice)
                if _paragraph_looks_like_code(block.text):
                    if in_list:
                        lines.append("")
                        in_list = False
                    lines.append("```swift")
                    lines.append(block.text)
                    lines.append("```")
                    lines.append("")
                    continue
                # For conceptual_strategy docs, aggressively filter "For more information..." paragraphs
                # even if they somehow passed initial filtering. These create false retrieval anchors.
                if page.doc_kind == "conceptual_strategy":
                    if _is_more_info_paragraph(block.text):
                        continue
                    if _is_marketing_summary_paragraph(block.text):
                        continue
                    cleaned_text = _remove_more_info_sentences(block.text)
                    if not cleaned_text.strip():
                        continue
                    cleaned_text = _normalize_text_typos(cleaned_text)
                    cleaned_text = _normalize_planning_bridge(cleaned_text)
                    block_text = _normalize_stylistic_prefixes(cleaned_text)
                    block_text = _capitalize_sentence_starts(block_text)
                else:
                    block_text = block.text
                
                if in_list:
                    # Close the list before the next paragraph.
                    lines.append("")
                    in_list = False
                if is_callout:
                    # First paragraph in a callout: keep heading and body in one logical
                    # block using a markdown line break. This helps RAG keep them together.
                    if callout_first_body:
                        if lines:
                            lines[-1] = lines[-1] + "  " + block_text
                        else:
                            lines.append(f"> {block_text}")
                        callout_first_body = False
                    else:
                        lines.append(f"> {block_text}")
                else:
                    lines.append(block_text)
                lines.append("")
            elif block.kind == "list_item":
                # Lists inside callouts: keep them as regular bullets (without `>`)
                # so that markdown parsers/chunkers do not lose list structure.
                if is_callout:
                    lines.append(f"- {block.text}")
                else:
                    # Skip breadcrumb-style bullets in the very first section:
                    # they duplicate the title/framework and add no semantic value.
                    # Check if this list item matches any breadcrumb or title/framework.
                    breadcrumb_set = set(page.breadcrumbs) if page.breadcrumbs else set()
                    if section_index == 0 and (
                        block.text in {page.title, page.framework or ""} or block.text in breadcrumb_set
                    ):
                        continue
                    lines.append(f"- {block.text}")
                in_list = True
            elif block.kind == "param":
                # Parameter block: render as "- `name`\n  description"
                if in_list:
                    lines.append("")
                    in_list = False
                param_name = block.param_name or "parameter"
                lines.append(f"- `{param_name}`")
                lines.append(f"  {block.text}")
                lines.append("")
            elif block.kind == "table":
                # Table block: render as markdown table (already formatted).
                # For strategy-style conceptual docs, defer table rendering to a
                # dedicated reference section at the end of the document to
                # reduce noise in the main flow.
                if page.doc_kind == "conceptual_strategy":
                    strategy_tables.append(block.text)
                    continue
                if in_list:
                    lines.append("")
                    in_list = False
                lines.append(block.text)
                lines.append("")
            elif block.kind == "code":
                # For macro API-reference pages, hide compiler macro signatures
                # (e.g. "@attached(...) macro Model()") from the main content.
                if page.doc_kind == "api_ref_macro" and _is_macro_compiler_signature(block.text):
                    continue

                if in_list:
                    # Close the list before code.
                    lines.append("")
                    in_list = False
                lang = block.language or ""
                # Code blocks inside callouts: render normally (callouts don't nest well with code).
                lines.append(f"```{lang}".rstrip())
                lines.append(block.text)
                lines.append("```")
                lines.append("")

        # Also close the list after the section, if it existed.
        if in_list:
            lines.append("")
            in_list = False

        # Ensure blank line separation between sections.
        if lines and lines[-1].strip():
            lines.append("")

    # For strategy-style conceptual docs, append collected tables as a compact
    # reference section at the end. This keeps the main narrative focused while
    # still preserving structured tabular data for cases where it is needed.
    if page.doc_kind == "conceptual_strategy" and strategy_tables:
        lines.append("## Reference tables (platform support)")
        lines.append("")
        for tbl in strategy_tables:
            # If the table was stored as one long line (no newlines), restore row
            # boundaries so markdown parsers see a proper table. Row boundary is
            # " | | " (one space between pipes); cell boundary is " |  | " (two).
            if tbl and "\n" not in tbl and "| --- " in tbl:
                tbl = re.sub(r" \| \| ", " |\n| ", tbl)
            for row in tbl.splitlines():
                lines.append(row)
            lines.append("")

    # Normalize excessive blank lines.
    md = "\n".join(lines)
    md = re.sub(r"\n{3,}", "\n\n", md).strip() + "\n"
    return md

