"""HTML parsing orchestration for Apple Developer documentation pages."""

from __future__ import annotations

import contextlib
from typing import Any, Dict, List, Optional

from webui_backend.apple_docs_fetcher import AppleDocRaw
from webui_backend.apple_docs_html import _HAS_LXML, _extract_text, _parse_table_to_markdown, lxml_html
from webui_backend.apple_docs_metadata import (
    _extract_availability_from_html,
    _extract_availability_from_initial_state,
    _extract_param_names_from_swift_signature,
    _is_macro_compiler_signature,
    _is_noise,
    _normalize_optional_func,
)
from webui_backend.apple_docs_models import AppleDocBlock, AppleDocPage, AppleDocSection
from webui_backend.apple_docs_scope import (
    _add_scope_markers_for_strategy,
    _deduplicate_by_semantic_role,
    _enhance_checklist_items,
    _is_ui_anchor_paragraph,
)
from webui_backend.apple_docs_sections import (
    _deduplicate_blocks_in_section,
    _deduplicate_h3_headings,
    _reassign_controls_paragraphs_for_strategy,
    _split_long_sections_for_strategy,
    _split_mixed_lists,
)
from webui_backend.apple_docs_text import (
    FRAMEWORK_MAP,
    _clean_title,
    _is_callout_heading,
    _is_more_info_paragraph,
    _norm_code,
)


def build_apple_doc_page(raw: AppleDocRaw) -> AppleDocPage:
    """
    Build a high-level structured representation of an Apple doc page.

    For now we:
    - Prefer a clean structural pass over `raw.main_html` via lxml.
    - Treat the first <h1> as the page title when `raw.title` is missing.
    - Build sections from headings (h1–h3) and body content (p, pre/code, li).
    - Ignore most of __INITIAL_STATE__ except for future extension hooks.
    """
    title = raw.title or ""
    sections: List[AppleDocSection] = []

    if not _HAS_LXML or not raw.main_html.strip():
        # Fallback: single-section page with raw HTML as a code block.
        section = AppleDocSection(heading=None, level=1)
        section.blocks.append(AppleDocBlock(kind="code", text=raw.main_html, language="html"))
        sections.append(section)
        return AppleDocPage(
            url=raw.url,
            title=title or raw.url,
            subtitle=None,
            framework=None,
            symbol=None,
            doc_kind=None,
            platforms=[],
            availability={},
            breadcrumbs=list(raw.breadcrumbs),
            sections=sections,
        )

    try:
        root = lxml_html.fromstring(raw.main_html)
    except Exception:  # noqa: BLE001
        section = AppleDocSection(heading=None, level=1)
        section.blocks.append(AppleDocBlock(kind="code", text=raw.main_html, language="html"))
        sections.append(section)
        return AppleDocPage(
            url=raw.url,
            title=title or raw.url,
            subtitle=None,
            framework=None,
            symbol=None,
            doc_kind=None,
            platforms=[],
            availability={},
            breadcrumbs=list(raw.breadcrumbs),
            sections=sections,
        )

    # Identify blocks in logical reading order.
    # Key points:
    # - use <pre> for block code examples;
    # - <code> inside <pre> is not handled as a separate block;
    # - standalone <code> (not in <pre>) is treated as inline (part of a paragraph) and
    #   is not added as a separate block;
    # - elements inside <li>/<ul>/<ol> are not processed separately (avoids duplication);
    # - tables are handled separately to avoid duplicating their contents.
    blocks = root.xpath(
        "//*[self::h1 or self::h2 or self::h3 "
        "or (self::p and not(ancestor::li) and not(ancestor::ul) and not(ancestor::ol) and not(ancestor::table)) "
        "or self::pre or self::li "
        "or (self::code and not(ancestor::pre) and not(ancestor::li) and not(ancestor::table))]"
    )
    
    # Find all tables separately to process them as structured blocks.
    # We exclude tables that are nested inside other tables or lists.
    table_elements = root.xpath("//table[not(ancestor::table) and not(ancestor::li)]")
    
    # Create a mapping of table elements to their markdown representation
    # for quick lookup during main processing loop.
    table_markdown_map: Dict[Any, str] = {}
    for table_el in table_elements:
        md_table = _parse_table_to_markdown(table_el)
        if md_table:
            table_markdown_map[table_el] = md_table
    
    # Combine blocks and tables, sort by document order for correct sequencing.
    all_elements = list(blocks) + list(table_elements)
    # Sort by document order (lxml provides getroottree() and getpath() for ordering)
    with contextlib.suppress(Exception):
        all_elements.sort(key=lambda el: el.getroottree().getpath(el))

    current_section: Optional[AppleDocSection] = None

    def ensure_section(level: int, heading_text: Optional[str]) -> AppleDocSection:
        """
        Create or return the current section.

        - If there is a new heading (heading_text not None), always create a new section
          with the given level.
        - If heading_text is missing but the section already exists, reuse it and
          keep the current level.
        - If heading_text is missing and the section does not exist yet, create an
          "unnamed" section with the specified level.
        """
        nonlocal current_section

        if heading_text is not None:
            current_section = AppleDocSection(heading=heading_text, level=level, blocks=[])
            sections.append(current_section)
            return current_section

        if current_section is None:
            current_section = AppleDocSection(heading=None, level=level, blocks=[])
            sections.append(current_section)

        return current_section

    # First pass: find explicit <h1> as page title if we don't have one.
    if not title:
        for el in blocks:
            tag = (el.tag or "").lower()
            if tag == "h1":
                maybe_title = _extract_text(el)
                if maybe_title:
                    title = maybe_title
                    break

    # Track code snippets we've already seen on this page to avoid
    # duplicating identical blocks (Apple docs often repeat the same
    # example multiple times in the DOM).
    seen_code_snippets: set[str] = set()
    
    # Collect Swift function signatures to extract parameter names for API reference pages.
    # This helps us match parameter descriptions with their names.
    swift_signatures: List[str] = []

    # Track whether this page looks like a macro API reference, based on
    # compiler-level macro signatures we see in code blocks.
    is_macro_page = False

    for el in all_elements:
        tag = (el.tag or "").lower()

        if tag in ("h1", "h2", "h3"):
            level = int(tag[1])
            heading_text = _extract_text(el)
            if level == 1:
                # Use h1 only as the title source, but do not create a separate section:
                # the page title will be a single (H1) in markdown.
                if heading_text and not title:
                    title = heading_text
                continue
            # Filter out blacklisted section headings (e.g., "See Also", "On This Page").
            if heading_text and _is_noise(heading_text):
                continue
            ensure_section(level=level, heading_text=heading_text or None)
            continue

        if tag == "p":
            text = _extract_text(el)
            if not text or _is_noise(text) or _is_more_info_paragraph(text) or _is_ui_anchor_paragraph(text):
                continue
            # Check if this paragraph is a callout heading (e.g., "Tip", "Important").
            # Apple docs often render callouts as standalone paragraphs.
            if _is_callout_heading(text):
                # Create a new section with this callout heading.
                ensure_section(level=3, heading_text=text.strip())
                continue
            level = current_section.level if current_section is not None else 2
            sect = ensure_section(level=level, heading_text=None)
            sect.blocks.append(AppleDocBlock(kind="paragraph", text=text))
            continue

        if tag == "li":
            text = _extract_text(el)
            if not text or _is_noise(text):
                continue
            level = current_section.level if current_section is not None else 2
            sect = ensure_section(level=level, heading_text=None)
            sect.blocks.append(AppleDocBlock(kind="list_item", text=text))
            continue

        if tag == "table":
            # Process tables as structured markdown blocks.
            if el in table_markdown_map:
                md_table = table_markdown_map[el]
                if md_table:
                    level = current_section.level if current_section is not None else 2
                    sect = ensure_section(level=level, heading_text=None)
                    sect.blocks.append(AppleDocBlock(kind="table", text=md_table))
            continue

        if tag == "code":
            # Inline code (not in <pre>): already included in the paragraph text via text_content,
            # we do not add it as a separate block.
            continue

        if tag == "pre":
            # Apple docs typically use Swift for code examples on these pages.
            raw_code = _extract_text(el)
            if not raw_code:
                continue

            # Filter out inline code snippets (single words/short identifiers without newlines).
            # These should be part of paragraph text, not separate code blocks.
            # Criteria: < 30 chars AND no newlines → likely inline code, skip.
            # Also skip single-word identifiers without operators/punctuation.
            is_short = len(raw_code) < 30
            has_newlines = "\n" in raw_code
            is_single_word = len(raw_code.split()) == 1 and not any(
                c in raw_code for c in ["(", ")", "[", "]", "{", "}", ".", ",", ":", ";", "=", "+", "-", "*", "/"]
            )

            if is_short and not has_newlines:
                # Too short and no structure → inline code, skip as separate block.
                continue
            if is_single_word and len(raw_code) < 50:
                # Single identifier without context → skip.
                continue

            # Mark macro pages when we see compiler-level macro signatures.
            if _is_macro_compiler_signature(raw_code):
                is_macro_page = True

            # De-duplicate identical code snippets within a single page.
            # This keeps one canonical copy of each example for RAG while
            # dropping repeated DOM copies.
            # Normalize whitespace/newlines for deduplication, but keep original
            # formatting in the output.
            normalized_code = _norm_code(raw_code)
            if normalized_code in seen_code_snippets:
                continue
            seen_code_snippets.add(normalized_code)

            # Normalize optional func for ObjC-interop methods.
            normalized_code_text, is_optional = _normalize_optional_func(raw_code)
            
            # Collect Swift function signatures (look for "func" keyword) for parameter extraction.
            if "func " in normalized_code_text.lower():
                swift_signatures.append(normalized_code_text)

            language = "swift"
            level = current_section.level if current_section is not None else 2
            sect = ensure_section(level=level, heading_text=None)
            # Store normalized code (without optional keyword) in the block.
            sect.blocks.append(AppleDocBlock(kind="code", text=normalized_code_text, language=language))
            continue

    # Post-process: enhance Parameters sections with parameter names.
    # Extract parameter names from Swift signatures we collected.
    param_names_from_signatures: List[str] = []
    for sig in swift_signatures:
        names = _extract_param_names_from_swift_signature(sig)
        if names:
            param_names_from_signatures.extend(names)
    
    # Process each "Parameters" section to add parameter names.
    for section in sections:
        if section.heading and section.heading.lower() == "parameters":
            # Try to find dt/dd structures in the DOM for this section.
            # We need to find the heading element and then look for dt/dd siblings.
            heading_elements = root.xpath("//h2[normalize-space(text())='Parameters'] | //h3[normalize-space(text())='Parameters']")
            
            param_blocks: List[AppleDocBlock] = []
            
            if heading_elements:
                heading_el = heading_elements[0]
                # Look for dt/dd pairs following this heading.
                # Apple docs often use <dl><dt>param</dt><dd>description</dd></dl>
                dl_elements = heading_el.xpath("./following-sibling::dl[1]")
                if dl_elements:
                    dl = dl_elements[0]
                    dts = dl.xpath(".//dt")
                    dds = dl.xpath(".//dd")
                    # Match dt/dd pairs
                    for i, dt in enumerate(dts):
                        param_name = _extract_text(dt).strip()
                        if i < len(dds):
                            param_desc = _extract_text(dds[i]).strip()
                            if param_name and param_desc:
                                param_blocks.append(
                                    AppleDocBlock(kind="param", text=param_desc, param_name=param_name)
                                )
            
            # Fallback: if we didn't find dt/dd, try to match existing paragraphs
            # with parameter names from signatures.
            if not param_blocks:
                # Get all paragraph blocks from this section.
                para_blocks = [b for b in section.blocks if b.kind == "paragraph"]
                if para_blocks and param_names_from_signatures:
                    # Match paragraphs with parameter names by position.
                    for i, para_block in enumerate(para_blocks):
                        if i < len(param_names_from_signatures):
                            param_name = param_names_from_signatures[i]
                            param_blocks.append(
                                AppleDocBlock(kind="param", text=para_block.text, param_name=param_name)
                            )
                        else:
                            # Keep as regular paragraph if no matching name.
                            param_blocks.append(para_block)
            
            # Replace paragraph blocks with enhanced param blocks if we found any.
            # Keep other block types (code, list_item, etc.) unchanged.
            if param_blocks:
                # Replace only paragraph blocks, keep others.
                new_blocks: List[AppleDocBlock] = []
                para_idx = 0
                for block in section.blocks:
                    if block.kind == "paragraph":
                        if para_idx < len(param_blocks):
                            new_blocks.append(param_blocks[para_idx])
                            para_idx += 1
                        # Skip original paragraph if we have a param replacement.
                    else:
                        # Keep non-paragraph blocks as-is.
                        new_blocks.append(block)
                # Add any remaining param blocks that weren't matched.
                while para_idx < len(param_blocks):
                    new_blocks.append(param_blocks[para_idx])
                    para_idx += 1
                section.blocks = new_blocks

    # Normalize heading levels for better RAG chunking.
    # If there are no explicit H2 sections but there are H3 sections,
    # promote H3→H2 (and deeper levels by one) so that top-level topics
    # become H2 anchors instead of a flat H3-only hierarchy.
    has_h2 = any(s.heading and s.level == 2 for s in sections)
    has_h3 = any(s.heading and s.level == 3 for s in sections)
    if not has_h2 and has_h3:
        for s in sections:
            if s.heading and s.level >= 3:
                s.level -= 1

    # Basic metadata placeholders; can be enhanced later using raw.initial_state.
    framework = None
    symbol = None
    doc_kind = None
    platforms: list[str] = []
    
    # Extract availability from __INITIAL_STATE__ (structured metadata only).
    # This is critical for LLM to understand API version requirements but must
    # never appear in prose/body content to avoid polluting embeddings.
    # Fallback to HTML parsing if not found in initial_state.
    availability: Dict[str, str] = _extract_availability_from_initial_state(raw.initial_state)
    if not availability:
        availability = _extract_availability_from_html(raw.main_html)

    # Heuristic: derive framework from breadcrumbs like ["SwiftData", "Preserving your app’s model data across launches"].
    if raw.breadcrumbs:
        framework = raw.breadcrumbs[0]

    # Fallback: extract framework from URL path if breadcrumbs are empty.
    if not framework:
        lower_url = raw.url.lower()
        if "/documentation/" in lower_url:
            # Extract framework name from URL: /documentation/swiftdata/... -> SwiftData
            parts = [p for p in lower_url.split("/documentation/")[-1].split("/") if p]
            if parts:
                seg = parts[0].lower()
                # Use known framework names, otherwise capitalize first letter.
                framework = FRAMEWORK_MAP.get(seg, seg[:1].upper() + seg[1:] if seg else None)

    # Heuristic: mark conceptual vs api_ref based on URL path.
    lower_url = raw.url.lower()
    slug = ""
    if "/documentation/" in lower_url:
        # API reference URLs typically have function signatures in the slug:
        # /documentation/uikit/uiview/addsubview(_:)
        # /documentation/foundation/url/init(string:)
        # Look for signature markers: parentheses, colons, underscores.
        slug = lower_url.rstrip("/").split("/")[-1]
        if any(x in slug for x in ("(", ")", ":", "_")) or slug in ("init", "deinit"):
            doc_kind = "api_ref"
        else:
            doc_kind = "conceptual"

    # Refine conceptual docs: detect "strategy"/planning-style conceptual pages.
    # These tend to be broad, strategic articles (e.g. "Developing a WidgetKit strategy")
    # that benefit from slightly different downstream handling (e.g. table placement).
    if doc_kind == "conceptual":
        slug_lower = slug
        title_lower = (title or "").lower()
        if "strategy" in slug_lower or "strategies" in slug_lower or "strategy" in title_lower:
            doc_kind = "conceptual_strategy"

    # Refine api_ref: detect macro API-reference pages and mark them separately.
    # This allows us to render macro docs in a more RAG-friendly way, hiding
    # compiler-level signatures and focusing on user-facing syntax.
    if doc_kind == "api_ref" and is_macro_page:
        doc_kind = "api_ref_macro"

    # For conceptual_strategy documents, apply aggressive structural improvements:
    # 1. Split long H2 sections into H3 subsections for better chunking
    # 2. Deduplicate H3 headings to merge duplicate subsections
    # 3. Split mixed lists into "considerations" vs "implementation" sections
    # 4. Enhance checklist items with context markers (before scope markers to avoid conflicts)
    # 5. Reassign mis-scoped paragraphs (e.g. Controls content under Live Activities)
    # 6. Add scope markers to H3 paragraphs for better retrieval precision
    # 7. Semantic deduplication to remove redundant content at meaning level
    # 8. Final deduplication pass to remove any remaining duplicate blocks
    if doc_kind == "conceptual_strategy":
        sections = _split_long_sections_for_strategy(sections)
        sections = _deduplicate_h3_headings(sections)
        sections = _split_mixed_lists(sections)
        sections = [_enhance_checklist_items(s) for s in sections]
        sections = _reassign_controls_paragraphs_for_strategy(sections)
        sections = _add_scope_markers_for_strategy(sections)
        sections = _deduplicate_by_semantic_role(sections)
        # Final deduplication pass on all sections
        sections = [_deduplicate_blocks_in_section(s) for s in sections]

    # Clean title: remove marketing/branding suffixes for better RAG retrieval.
    cleaned_title = _clean_title(title or raw.url)

    return AppleDocPage(
        url=raw.url,
        title=cleaned_title,
        subtitle=None,
        framework=framework,
        symbol=symbol,
        doc_kind=doc_kind,
        platforms=platforms,
        availability=availability,
        breadcrumbs=list(raw.breadcrumbs),
        sections=sections,
    )


