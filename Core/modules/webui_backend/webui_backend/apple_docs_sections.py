"""Section-level transforms for Apple docs extraction."""

from __future__ import annotations

from typing import List, Optional

from webui_backend.apple_docs_models import AppleDocBlock, AppleDocSection
from webui_backend.apple_docs_text import (
    _normalize_text_typos,
    _should_start_h3_subsection,
)


def _deduplicate_blocks_in_section(section: AppleDocSection) -> AppleDocSection:
    """
    Remove duplicate blocks within a section based on normalized text content.
    This prevents duplicate paragraphs and other blocks from appearing in the output.
    Also fixes common typos in block text.
    """
    seen_texts: set[str] = set()
    deduplicated_blocks: List[AppleDocBlock] = []
    
    for block in section.blocks:
        # Normalize text for comparison (strip whitespace, lowercase)
        # Also fix typos in the text
        if block.text:
            block_text = _normalize_text_typos(block.text)
            normalized_text = " ".join(block_text.strip().split()).lower()
        else:
            normalized_text = ""
            block_text = block.text
        
        # Skip empty blocks
        if not normalized_text:
            continue
        
        # Skip if we've seen this exact text before
        if normalized_text in seen_texts:
            continue
        
        seen_texts.add(normalized_text)
        
        # Create new block with normalized text if it was modified
        if block_text != block.text:
            new_block = AppleDocBlock(
                kind=block.kind,
                text=block_text,
                language=block.language,
                param_name=block.param_name,
                table_data=block.table_data
            )
            deduplicated_blocks.append(new_block)
        else:
            deduplicated_blocks.append(block)
    
    return AppleDocSection(
        heading=section.heading,
        level=section.level,
        blocks=deduplicated_blocks
    )


def _reassign_controls_paragraphs_for_strategy(
    sections: List[AppleDocSection],
) -> List[AppleDocSection]:
    """
    For conceptual_strategy documents, reassign paragraphs that clearly talk
    about controls/Control Center out of the 'Live Activities' subsection
    into the 'Controls' subsection. This reduces scope drift where content
    about controls sits under a Live Activities heading.
    """
    # Find the Controls subsection once.
    controls_idx: Optional[int] = None
    for idx, section in enumerate(sections):
        if (
            section.level == 3
            and section.heading
            and "controls" in section.heading.lower()
        ):
            controls_idx = idx
            break

    if controls_idx is None:
        return sections

    controls_section = sections[controls_idx]

    # Identify Live Activities subsections.
    live_indices: List[int] = [
        idx
        for idx, section in enumerate(sections)
        if section.level == 3
        and section.heading
        and "live activities" in section.heading.lower()
    ]

    if not live_indices:
        return sections

    moved_any = False

    for idx in live_indices:
        section = sections[idx]
        new_blocks: List[AppleDocBlock] = []

        for block in section.blocks:
            if block.kind == "paragraph" and block.text:
                lower = block.text.lower()
                # Heuristic: paragraphs that talk about Control Center / controls /
                # menu bar items / Action button are really about Controls, not
                # Live Activities.
                if any(
                    key in lower
                    for key in (
                        "control center",
                        "controls ",
                        " controls,",
                        "menu bar items",
                        "action button of apple watch ultra",
                    )
                ):
                    controls_section.blocks.append(block)
                    moved_any = True
                    continue
            new_blocks.append(block)

        if moved_any:
            sections[idx] = AppleDocSection(
                heading=section.heading,
                level=section.level,
                blocks=new_blocks,
            )

    if moved_any:
        sections[controls_idx] = controls_section

    return sections


def _deduplicate_h3_headings(sections: List[AppleDocSection]) -> List[AppleDocSection]:
    """
    For conceptual_strategy documents, merge H3 subsections with duplicate headings
    within the same H2 parent section. This prevents duplicate "Live Activities" or
    "Widget extension setup" sections.
    """
    result: List[AppleDocSection] = []
    i = 0
    
    while i < len(sections):
        section = sections[i]
        
        # If this is an H2 section, check for duplicate H3 subsections that follow
        if section.level == 2 and section.heading:
            h2_section = section
            h3_subsections: List[AppleDocSection] = []
            seen_h3_headings: dict[str, AppleDocSection] = {}  # heading -> merged section
            
            # Collect all H3 subsections that belong to this H2
            j = i + 1
            while j < len(sections) and sections[j].level == 3:
                h3_section = sections[j]
                
                if h3_section.heading:
                    # Check if we've seen this heading before
                    heading_lower = h3_section.heading.lower()
                    if heading_lower in seen_h3_headings:
                        # Merge blocks into existing section
                        seen_h3_headings[heading_lower].blocks.extend(h3_section.blocks)
                    else:
                        # First occurrence of this heading
                        seen_h3_headings[heading_lower] = h3_section
                        h3_subsections.append(h3_section)
                else:
                    # H3 without heading - add to last subsection or create new one
                    if h3_subsections:
                        h3_subsections[-1].blocks.extend(h3_section.blocks)
                    else:
                        h3_subsections.append(h3_section)
                
                j += 1
            
            # Add H2 section and deduplicated H3 subsections
            result.append(h2_section)
            result.extend(h3_subsections)
            i = j
        else:
            # Not an H2 section, add as-is
            result.append(section)
            i += 1
    
    return result


def _split_long_sections_for_strategy(sections: List[AppleDocSection]) -> List[AppleDocSection]:
    """
    For conceptual_strategy documents, split long H2 sections into H3 subsections
    based on paragraph patterns. This improves RAG chunking by creating smaller,
    more focused semantic units.
    
    A section is considered "long" if it has > 5 paragraph blocks without H3 subsections.
    """
    result: List[AppleDocSection] = []
    
    for section in sections:
        # Deduplicate blocks in the section first
        section = _deduplicate_blocks_in_section(section)
        # Only process H2 sections (level 2) that have many paragraphs
        if section.level != 2 or not section.heading:
            result.append(section)
            continue
        
        para_blocks = [b for b in section.blocks if b.kind == "paragraph"]
        # If section has <= 5 paragraphs, keep as-is
        if len(para_blocks) <= 5:
            result.append(section)
            continue
        
        # Split into subsections based on paragraph patterns
        new_subsections: List[AppleDocSection] = []
        current_subsection: Optional[AppleDocSection] = None
        initial_blocks: List[AppleDocBlock] = []  # Blocks before first H3 pattern
        
        for block in section.blocks:
            if block.kind == "paragraph":
                h3_heading = _should_start_h3_subsection(block.text)
                if h3_heading:
                    # Start a new H3 subsection
                    # First, save any initial blocks to the first subsection if we haven't created any yet
                    if initial_blocks and not new_subsections and not current_subsection:
                        # Create first subsection with initial content
                        current_subsection = AppleDocSection(
                            heading=None,
                            level=3,
                            blocks=initial_blocks.copy()
                        )
                        new_subsections.append(current_subsection)
                        initial_blocks = []
                    
                    # Close current subsection and start new one
                    if current_subsection:
                        new_subsections.append(current_subsection)
                    current_subsection = AppleDocSection(
                        heading=h3_heading,
                        level=3,
                        blocks=[block]
                    )
                else:
                    # Add to current subsection or collect as initial content
                    if current_subsection:
                        current_subsection.blocks.append(block)
                    elif new_subsections:
                        # Add to last subsection
                        new_subsections[-1].blocks.append(block)
                    else:
                        # Collect as initial content (before first H3 pattern)
                        initial_blocks.append(block)
            else:
                # Non-paragraph blocks (code, lists, tables) → add to current subsection
                if current_subsection:
                    current_subsection.blocks.append(block)
                elif new_subsections:
                    new_subsections[-1].blocks.append(block)
                else:
                    # Collect as initial content
                    initial_blocks.append(block)
        
        # Add final subsection
        if current_subsection:
            new_subsections.append(current_subsection)
        
        # If we created subsections, replace the original section
        if new_subsections:
            # Keep the original H2 heading as parent section.
            # If we have initial blocks, add them to the first subsection (not to H2)
            # to avoid duplication and keep H2 as a clean parent header.
            if initial_blocks:
                # Prepend initial blocks to the first subsection
                new_subsections[0].blocks = initial_blocks + new_subsections[0].blocks
            
            # Create H2 header (empty or with minimal content to ensure it renders)
            h2_header = AppleDocSection(
                heading=section.heading,
                level=2,
                blocks=[]  # Empty - all content in H3 subsections
            )
            result.append(h2_header)
            
            # Add all H3 subsections
            result.extend(new_subsections)
        else:
            # No subsections created → keep original
            result.append(section)
    
    return result


def _split_mixed_lists(sections: List[AppleDocSection]) -> List[AppleDocSection]:
    """
    For conceptual_strategy documents, detect and split mixed lists that contain
    both "What to consider" items and "How to implement" items.
    
    Pattern: Lists that mix items starting with "To create", "To add", "To offer"
    (implementation) with items that don't start with "To" (considerations).
    """
    result: List[AppleDocSection] = []
    
    for section in sections:
        new_blocks: List[AppleDocBlock] = []
        i = 0
        
        while i < len(section.blocks):
            block = section.blocks[i]
            
            # Check if this is a list_item block
            if block.kind == "list_item":
                # Collect consecutive list items
                list_items: List[AppleDocBlock] = [block]
                i += 1
                while i < len(section.blocks) and section.blocks[i].kind == "list_item":
                    list_items.append(section.blocks[i])
                    i += 1
                
                # Check if list mixes "To..." (implementation) with non-"To..." (considerations)
                implementation_items: List[AppleDocBlock] = []
                consideration_items: List[AppleDocBlock] = []
                
                for item in list_items:
                    text_lower = item.text.lower().strip()
                    # Implementation items:
                    # - Start with "To create", "To add", "To offer", "To provide", "To start"
                    # - Describe platform-specific rendering/behavior: "On the Home Screen", "On the Lock Screen", 
                    #   "In CarPlay", "On Mac", "On Apple Watch", "On iPhone", "On iPad"
                    is_implementation = (
                        text_lower.startswith(("to create", "to add", "to offer", "to provide", "to start", "to use")) or
                        text_lower.startswith(("on the home screen", "on the lock screen", "in carplay", 
                                               "on mac", "on apple watch", "on iphone", "on ipad", 
                                               "on older versions", "on devices that run"))
                    )
                    if is_implementation:
                        implementation_items.append(item)
                    else:
                        consideration_items.append(item)
                
                # If we have both types, split them
                if implementation_items and consideration_items:
                    # Add consideration items first with a bridging sentence
                    if consideration_items:
                        new_blocks.append(AppleDocBlock(
                            kind="paragraph",
                            text="Consider the following aspects:"
                        ))
                        new_blocks.extend(consideration_items)
                    
                    # Add bridging text and implementation items
                    if implementation_items:
                        # Add a bridging paragraph
                        new_blocks.append(AppleDocBlock(
                            kind="paragraph",
                            text="Implementation guidelines:"
                        ))
                        new_blocks.extend(implementation_items)
                else:
                    # No split needed, keep as-is
                    new_blocks.extend(list_items)
            else:
                # Non-list block → keep as-is
                new_blocks.append(block)
                i += 1
        
        # Create new section with processed blocks
        new_section = AppleDocSection(
            heading=section.heading,
            level=section.level,
            blocks=new_blocks
        )
        result.append(new_section)
    
    return result


