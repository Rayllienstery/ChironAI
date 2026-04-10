"""
Apple Developer documentation → structured model → RAG-optimized Markdown.

This module is intentionally Apple-aware but conservative: it prefers
stable, deterministic structure over clever heuristics. It works primarily
from the rendered HTML provided by `apple_docs_fetcher.AppleDocRaw.main_html`
and can optionally incorporate hints from `initial_state`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import json
import re

try:
    from lxml import html as lxml_html  # type: ignore[import]

    _HAS_LXML = True
except ImportError:  # pragma: no cover - environment without lxml
    lxml_html = None  # type: ignore[assignment]
    _HAS_LXML = False

from apple_docs_fetcher import AppleDocRaw


@dataclass
class AppleDocBlock:
    kind: str  # "paragraph", "code", "list_item", "table", "param"
    text: str
    language: Optional[str] = None  # for code blocks
    param_name: Optional[str] = None  # for param blocks: the parameter name
    table_data: Optional[List[List[str]]] = None  # for table blocks: rows of cells


@dataclass
class AppleDocSection:
    heading: Optional[str]
    level: int  # 1..6, where 1 is page title, 2+ are subsections
    blocks: List[AppleDocBlock] = field(default_factory=list)


@dataclass
class AppleDocPage:
    url: str
    title: str
    subtitle: Optional[str]
    framework: Optional[str]
    symbol: Optional[str]
    # Known values include:
    # - "conceptual" — general conceptual articles
    # - "conceptual_strategy" — strategy/planning docs (e.g. WidgetKit strategy)
    # - "api_ref" — API reference for types/functions/methods
    # - "api_ref_macro" — API reference for Swift macros
    doc_kind: Optional[str]
    platforms: List[str]
    availability: Dict[str, str]  # e.g. {"iOS": "17.0+", "macOS": "14.0+", "Swift": "5.9+"}
    breadcrumbs: List[str]
    sections: List[AppleDocSection]


def _extract_text(el) -> str:
    return (el.text_content() or "").strip()


def _parse_table_to_markdown(table_el) -> str:
    """
    Parse an HTML <table> element into markdown table format.
    
    Returns markdown table string, or empty string if parsing fails.
    """
    if not _HAS_LXML:
        return ""
    
    try:
        rows = []
        # Get all rows (both thead and tbody)
        trs = table_el.xpath(".//tr")
        
        for tr in trs:
            cells = []
            # Get all cells (th or td)
            for cell in tr.xpath(".//th | .//td"):
                cell_text = _extract_text(cell)
                # Clean up whitespace and newlines
                cell_text = " ".join(cell_text.split())
                cells.append(cell_text)
            
            if cells:  # Only add non-empty rows
                rows.append(cells)
        
        if not rows:
            return ""
        
        # Determine column count (use max to handle irregular tables)
        max_cols = max(len(row) for row in rows) if rows else 0
        if max_cols == 0:
            return ""
        
        # Normalize all rows to have the same number of columns
        normalized_rows = []
        for row in rows:
            normalized = row + [""] * (max_cols - len(row))
            normalized_rows.append(normalized[:max_cols])
        
        # Build markdown table
        lines = []
        
        # Header row
        if normalized_rows:
            header = normalized_rows[0]
            lines.append("| " + " | ".join(header) + " |")
            # Separator row
            lines.append("| " + " | ".join(["---"] * max_cols) + " |")
            # Data rows
            for row in normalized_rows[1:]:
                lines.append("| " + " | ".join(row) + " |")
        
        md = "\n".join(lines)

        # Safety: some odd tables in Apple docs can end up flattened into a
        # single physical line with repeated "| --- |" and data rows. As a
        # last-resort fix, split such constructs back into one-row-per-line
        # form so markdown/table parsers see a proper structure.
        if "\n" not in md and "| --- " in md:
            import re
            md = re.sub(r"\|\s+\|", "|\n|", md)
        
        return md
    
    except Exception:  # noqa: BLE001
        return ""


# Blacklist patterns: any text matching these substrings is UI/navigation noise
# and should be filtered out before adding to RAG.
BLACKLIST_PATTERNS = [
    "On This Page",
    "Jump to",
    "Beta Software",
    "Requires JavaScript",
    "Learn more",
    "See Also",
    "Copy to Clipboard",
    "Copy",
    "Copy Code",
    "Beta",
    "New in ",
    "View in English",
    "View in Russian",
    "Table of Contents",
    "Contents",
    "Related Documentation",
    "Related Topics",
    "Related Articles",
    "Download Sample Code",
    "Download",
    "Get Started",
    "Overview",
    "Documentation",
    "API Reference",
    "Guides",
    "Sample Code",
    "Videos",
    "Forums",
    "Feedback",
    "Sign In",
    "Sign Out",
    "Account",
    "Search",
    "Menu",
    "Navigation",
    "Skip to content",
    "Skip navigation",
    "Close",
    "Open",
    "Expand",
    "Collapse",
    "Show more",
    "Show less",
    "Previous",
    "Next",
    "Back",
    "Forward",
    "Top",
    "Bottom",
    "Scroll to top",
    "Scroll to bottom",
]

FRAMEWORK_MAP = {
    "swiftui": "SwiftUI",
    "uikit": "UIKit",
    "foundation": "Foundation",
    "swiftdata": "SwiftData",
    "combine": "Combine",
    "swift": "Swift",
    "coredata": "CoreData",
    "coreanimation": "CoreAnimation",
    "avfoundation": "AVFoundation",
    "mapkit": "MapKit",
    "coregraphics": "CoreGraphics",
    "storekit": "StoreKit",
}


def _norm_code(s: str) -> str:
    """
    Normalize code snippet for deduplication: collapse whitespace and newlines.
    This helps catch duplicates that differ only in formatting.
    """
    s = s.strip()
    # Collapse multiple spaces/tabs to single space.
    s = re.sub(r"[ \t]+", " ", s)
    # Collapse 3+ newlines to double newline.
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s


def _clean_title(title: str) -> str:
    """
    Remove marketing/branding suffixes from page titles for better RAG retrieval.
    
    Examples:
    "Preserving your app's model data across launches | Apple Developer Documentation"
    -> "Preserving your app's model data across launches"
    """
    if not title:
        return title
    # Remove common Apple docs branding suffixes.
    title = re.sub(r"\s*\|\s*Apple Developer Documentation.*$", "", title, flags=re.IGNORECASE)
    title = re.sub(r"\s*\|\s*Apple.*$", "", title, flags=re.IGNORECASE)
    return title.strip()


def _is_callout_heading(heading: str) -> bool:
    """
    Check if a heading is a callout type (Tip, Important, Note, Warning, etc.).
    """
    if not heading:
        return False
    callouts = ("tip", "important", "note", "warning", "caution", "deprecated", "experimental")
    return heading.strip().lower() in callouts


def _is_more_info_paragraph(text: str) -> bool:
    """
    Detect neutral \"For more information...\" tails that don't add semantic value
    but consume tokens in embeddings.

    Examples:
    \"For more information, see ModelContext.\"
    \"For additional information, refer to ActivityKit.\"
    \"For more information, refer to Preparing widgets for additional platforms, contexts, and appearances.\"
    
    This function filters ALL such paragraphs regardless of length, as they are
    purely referential and create false retrieval anchors for RAG.
    """
    if not text:
        return False
    normalized = " ".join(text.split())
    lower = normalized.lower()
    # We target sentences that start with these phrases and do NOT contain explicit URLs.
    # For RAG, these are noise regardless of length — they're references, not knowledge.
    # Patterns include variations like "For more information on..." and "For additional information about..."
    starts = (
        "for more information, see ",
        "for more information see ",
        "for more information, refer to ",
        "for more information on ",
        "for additional information, see ",
        "for additional information, refer to ",
        "for additional information about ",
    )
    if not any(lower.startswith(s) for s in starts):
        return False
    if "http://" in normalized or "https://" in normalized:
        return False
    # Filter ALL such paragraphs — they're references, not content.
    # No length limit: even long ones like "For more information, refer to Preparing widgets..."
    # should be filtered as they create false retrieval anchors.
    return True


def _remove_more_info_sentences(text: str) -> str:
    """
    Remove \"For more information...\" sentences from paragraphs that contain them.
    This is more aggressive than filtering entire paragraphs: it preserves the
    useful content while removing only the referential noise.
    
    Example:
    Input: \"Widgets use timelines. For more information, refer to ActivityKit.\"
    Output: \"Widgets use timelines.\"
    
    Input: \"Widgets use timelines. For more information on how timelines work, refer to ActivityKit.\"
    Output: \"Widgets use timelines.\"
    """
    if not text:
        return text
    import re
    
    # Pattern to match "For more information..." sentences.
    # Matches from the start of a sentence (after period/space or start of string)
    # through the end of the sentence (period/exclamation/question mark).
    patterns = [
        r'\s*For more information,?\s+see\s+[^.!?]+[.!?]',
        r'\s*For more information,?\s+refer to\s+[^.!?]+[.!?]',
        r'\s*For more information\s+on\s+[^.!?]+[.!?]',
        r'\s*For additional information,?\s+see\s+[^.!?]+[.!?]',
        r'\s*For additional information,?\s+refer to\s+[^.!?]+[.!?]',
        r'\s*For additional information\s+about\s+[^.!?]+[.!?]',
    ]
    
    result = text
    for pattern in patterns:
        # Case-insensitive match
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    # Clean up multiple spaces and trailing/leading whitespace
    result = re.sub(r'\s+', ' ', result)
    result = result.strip()
    
    # Also handle cases where the entire text is just a "For more information..." sentence
    if _is_more_info_paragraph(result):
        return ""
    
    return result


def _is_marketing_summary_paragraph(text: str) -> bool:
    """
    Detect high-level marketing/summary paragraphs that don't add API/constraints/rules.
    For engineering RAG these are weak signal and can be filtered.
    """
    if not text:
        return False
    lower = " ".join(text.split()).lower()
    if "use widgetkit to build" in lower and "becomes part of the widget ecosystem" in lower:
        return True
    return False


def _normalize_planning_bridge(text: str) -> str:
    """
    Remove dangling planning clause that expects a list but is not followed by one.
    "As you make your plans, take into account:" creates a semantic gap when the
    list lives in another section. Strip it so the paragraph ends with the
    actionable sentence only.
    """
    if not text:
        return text
    import re
    # Remove "As you make your plans, take into account:" (and "When planning adoption, consider:")
    # so we don't leave "consider:" with nothing after it.
    text = re.sub(
        r'\s*(?:As you make your plans, take into account|When planning adoption, consider):\s*$',
        '',
        text,
        flags=re.IGNORECASE
    )
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _normalize_stylistic_prefixes(text: str) -> str:
    """
    Normalize weak stylistic prefixes that add noise for RAG but
    don't change semantics (e.g. repeated "Additionally, ").

    This operates at the sentence boundary level and is intentionally
    conservative: it only strips the discourse marker and keeps the
    actual factual content intact.
    """
    if not text:
        return text

    import re

    # Drop "Additionally, " at the start of a sentence while keeping the rest.
    # Examples:
    # "Additionally, widgets can update their data..." -> "Widgets can also update their data..."
    # "..., power. Additionally, widgets can update..." -> "..., power. Widgets can also update..."
    text = re.sub(r'(^|\.\s+)[Aa]dditionally,\s+', r'\1', text)
    # Restore "also" where we stripped "Additionally, widgets" -> "Widgets can also"
    text = re.sub(r'(^|\.\s+)widgets can update\b', r'\1Widgets can also update', text, flags=re.IGNORECASE)

    return text


def _capitalize_sentence_starts(text: str) -> str:
    """
    Capitalize the first letter after sentence boundaries (. ) and after
    scope markers (: ). This fixes degraded capitalization after stripping
    "Additionally," and keeps LLM/embedding confidence high.
    """
    if not text:
        return text
    import re
    # Capitalize first character if letter
    if text[0].isalpha():
        text = text[0].upper() + text[1:]
    # After ". " or ": " capitalize the next letter
    def _upper_after(match):
        return match.group(1) + match.group(2).upper()
    text = re.sub(r'(\.\s+|\:\s+)([a-z])', _upper_after, text)
    return text

def _should_start_h3_subsection(text: str) -> Optional[str]:
    """
    Heuristically detect if a paragraph should start a new H3 subsection
    in a long H2 section for conceptual_strategy documents.
    
    Returns the H3 heading text if this paragraph should start a subsection,
    None otherwise.
    
    Patterns:
    - "Widgets and Live Activities..." → "Widgets and Live Activities"
    - "Live Activities don't..." → "Live Activities"
    - "Controls also..." → "Controls"
    - "By default, people tap..." → "Deep linking"
    - "Widgets offer direct interaction..." → "Interactivity"
    - "To add widgets..." → "Widget extension setup"
    - "To avoid costly changes..." → "Planning adoption"
    """
    if not text:
        return None
    normalized = " ".join(text.split())
    lower = normalized.lower()
    
    # Pattern matching for common topic starters
    if lower.startswith("widgets and live activities"):
        return "Widgets and Live Activities"
    if lower.startswith("live activities"):
        return "Live Activities"
    if lower.startswith("controls"):
        return "Controls"
    if lower.startswith("by default, people tap") or "deep linking" in lower[:100]:
        return "Deep linking"
    if lower.startswith("widgets offer direct interaction") or ("app intents" in lower[:100] and "interaction" in lower[:100]):
        return "Interactivity"
    if lower.startswith("make it possible for people to select") or "configurable widgets" in lower[:100]:
        return "Configuration"
    if lower.startswith("on iphone and ipad, people create stacks") or "smart stacks" in lower[:100]:
        return "Smart Stacks"
    if lower.startswith("to add widgets") or "widget extension" in lower[:100]:
        return "Widget extension setup"
    if lower.startswith("to avoid costly changes") or "plan your widgetkit adoption" in lower[:100]:
        return "Planning adoption"
    if lower.startswith("the lock screen") or "always on" in lower[:100]:
        return "Privacy and visibility"
    
    return None


def _normalize_text_typos(text: str) -> str:
    """
    Fix common typos and duplicate phrases in text.
    Examples: "it uses it uses" -> "it uses", "inclusing" -> "including"
    """
    if not text:
        return text
    
    import re
    # Common typos (word boundary so we don't break mid-word)
    text = re.sub(r'\binclusing\b', 'including', text, flags=re.IGNORECASE)
    
    # Fix duplicate phrases (common typo pattern: "word word" -> "word")
    text = re.sub(r'\b(\w+(?:\s+\w+){0,3})\s+\1\b', r'\1', text, flags=re.IGNORECASE)
    
    # Fix common duplicate words
    text = re.sub(r'\b(\w+)\s+\1\b', r'\1', text, flags=re.IGNORECASE)
    
    # Normalize multiple spaces
    text = re.sub(r'\s+', ' ', text)
    
    return text.strip()


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


def _extract_scope_from_h3_heading(heading: str) -> Optional[str]:
    """
    Extract scope/subject from H3 heading for conceptual_strategy documents.
    Returns the main subject (Widgets, Live Activities, Controls, etc.)
    to use as a scope marker for paragraphs in that section.
    
    Examples:
    "Widgets and Live Activities" -> "Widgets and Live Activities"
    "Live Activities" -> "Live Activities"
    "Controls" -> "Controls"
    "Deep linking" -> None (too generic)
    "Interactivity" -> None (too generic)
    """
    if not heading:
        return None
    
    heading_lower = heading.lower()
    
    # Specific scopes that should be marked
    specific_scopes = [
        "widgets and live activities",
        "live activities",
        "controls",
        "widget extension setup",
        "smart stacks",
        "privacy and visibility",
        "planning adoption",
    ]
    
    for scope in specific_scopes:
        if scope in heading_lower or heading_lower == scope:
            # Capitalize properly
            if scope == "widgets and live activities":
                return "Widgets and Live Activities"
            elif scope == "live activities":
                return "Live Activities"
            elif scope == "controls":
                # Do not add "Controls:" prefix — section heading is already ### Controls.
                return None
            elif scope == "widget extension setup":
                return "Widgets"
            elif scope == "smart stacks":
                return "Smart Stacks"
            elif scope == "privacy and visibility":
                return "Widgets"
            elif scope == "planning adoption":
                return None  # Too generic
    
    return None


def _paragraph_mentions_different_subject(text: str, current_scope: str) -> bool:
    """
    Check if a paragraph explicitly mentions a different subject than the current scope.
    This prevents adding incorrect scope markers.
    
    Example:
    current_scope = "Live Activities"
    text = "In iOS, iPadOS, and macOS, your app can offer controls..."
    -> Returns True (mentions "controls", not "Live Activities")
    """
    if not text or not current_scope:
        return False
    
    text_lower = text.lower()
    scope_lower = current_scope.lower()
    
    # Other subjects that might be mentioned
    other_subjects = {
        "widgets": ["widget", "widgets", "widgetkit"],
        "live activities": ["live activity", "live activities", "activitykit"],
        "controls": ["control", "controls", "control center"],
        "smart stacks": ["smart stack", "smart stacks"],
    }
    
    # Check if text mentions a different subject prominently
    for subject, keywords in other_subjects.items():
        if subject != scope_lower:
            # Check if any keyword appears in first 150 chars
            first_part = text_lower[:150]
            if any(keyword in first_part for keyword in keywords):
                # Check if current scope is NOT mentioned in first 150 chars
                scope_keywords = other_subjects.get(scope_lower, [scope_lower])
                if not any(keyword in first_part for keyword in scope_keywords):
                    return True
    
    return False


def _add_scope_markers_to_section(section: AppleDocSection, _parent_h2_heading: Optional[str] = None) -> AppleDocSection:
    """
    Add scope markers to paragraphs in H3 sections for conceptual_strategy documents.
    This improves retrieval precision by making the subject explicit.
    
    Example:
    Input: "They use a timeline of data updates..."
    Output: "Widgets: They use a timeline of data updates..."
    """
    if section.level != 3 or not section.heading:
        return section
    
    scope = _extract_scope_from_h3_heading(section.heading)
    if not scope:
        return section
    
    new_blocks: List[AppleDocBlock] = []
    for block in section.blocks:
        if block.kind == "paragraph" and block.text:
            # Skip bridging paragraphs (Consider the following, Implementation guidelines, etc.)
            text_lower = block.text.lower().strip()
            bridging_patterns = [
                "consider the following",
                "implementation guidelines",
                "consider the following aspects",
            ]
            if any(pattern in text_lower for pattern in bridging_patterns):
                new_blocks.append(block)
                continue
            
            # Skip if paragraph mentions a different subject
            if _paragraph_mentions_different_subject(block.text, scope):
                new_blocks.append(block)
                continue
            
            # Check if paragraph already starts with scope marker
            if not text_lower.startswith(scope.lower() + ":") and not text_lower.startswith(scope.lower() + " "):
                # Only add scope marker if paragraph is substantial (> 50 chars)
                # Add scope marker if scope is not mentioned in first 50 chars (more aggressive)
                if len(block.text) > 50:
                    first_part = block.text[:50].lower()
                    scope_keywords = {
                        "widgets and live activities": ["widget", "widgets", "live activity"],
                        "live activities": ["live activity", "live activities"],
                        "controls": ["control", "controls"],
                        "widgets": ["widget", "widgets"],
                        "smart stacks": ["smart stack", "smart stacks"],
                    }
                    keywords = scope_keywords.get(scope.lower(), [scope.lower()])
                    if not any(keyword in first_part for keyword in keywords):
                        # Add scope marker
                        new_text = f"{scope}: {block.text}"
                        new_block = AppleDocBlock(
                            kind=block.kind,
                            text=new_text,
                            language=block.language,
                            param_name=block.param_name,
                            table_data=block.table_data
                        )
                        new_blocks.append(new_block)
                    else:
                        new_blocks.append(block)
                else:
                    new_blocks.append(block)
            else:
                new_blocks.append(block)
        else:
            new_blocks.append(block)
    
    return AppleDocSection(
        heading=section.heading,
        level=section.level,
        blocks=new_blocks
    )


def _add_scope_markers_for_strategy(sections: List[AppleDocSection]) -> List[AppleDocSection]:
    """
    Add scope markers to all H3 subsections in conceptual_strategy documents.
    """
    result: List[AppleDocSection] = []
    i = 0
    
    while i < len(sections):
        section = sections[i]
        
        if section.level == 2:
            # H2 section - add it and process following H3 subsections
            result.append(section)
            i += 1
            
            # Process all following H3 subsections
            while i < len(sections) and sections[i].level == 3:
                h3_section = sections[i]
                enhanced_section = _add_scope_markers_to_section(h3_section, section.heading)
                result.append(enhanced_section)
                i += 1
        else:
            # Other sections (H1, H4+, or orphaned sections)
            result.append(section)
            i += 1
    
    return result


def _is_checklist_list_item(text: str) -> bool:
    """
    Detect if a list item is a checklist item (enumeration without expansion).
    These are typically short, high-level items that need context.
    
    Examples:
    - "Feature availability for each platform" -> True
    - "To create the user interface..." -> False (implementation, not checklist)
    - "On the Home Screen..." -> False (specific detail, not checklist)
    """
    if not text:
        return False
    
    text_lower = text.lower().strip()
    
    # Checklist items are typically:
    # - Short (< 100 chars)
    # - Don't start with "To" (not implementation)
    # - Don't start with "On the" / "In" (not platform-specific detail)
    # - Are high-level concepts
    
    if len(text) > 100:
        return False
    
    if text_lower.startswith(("to ", "on the ", "in ", "on mac", "on iphone", "on ipad", "on apple watch")):
        return False
    
    # High-level checklist patterns
    checklist_patterns = [
        "availability",
        "framework",
        "appearance",
        "size",
        "technology",
        "animation",
        "interactivity",
        "configuration",
        "visibility",
        "constraint",
        "requirement",
    ]
    
    return any(pattern in text_lower for pattern in checklist_patterns)


def _enhance_checklist_items(section: AppleDocSection) -> AppleDocSection:
    """
    Enhance checklist items by adding context markers for conceptual_strategy documents.
    This helps LLM understand that these are high-level considerations, not detailed instructions.
    """
    new_blocks: List[AppleDocBlock] = []
    i = 0
    
    while i < len(section.blocks):
        block = section.blocks[i]
        
        if block.kind == "list_item":
            # Collect consecutive list items
            list_items: List[AppleDocBlock] = [block]
            i += 1
            while i < len(section.blocks) and section.blocks[i].kind == "list_item":
                list_items.append(section.blocks[i])
                i += 1
            
            # Check if these are checklist items
            checklist_items: List[AppleDocBlock] = []
            other_items: List[AppleDocBlock] = []
            
            for item in list_items:
                if _is_checklist_list_item(item.text):
                    checklist_items.append(item)
                else:
                    other_items.append(item)
            
            # If we have checklist items, add context only if not already present
            if checklist_items and len(checklist_items) >= 3:
                # Check if previous block is already a context paragraph
                has_context = False
                if new_blocks:
                    last_block = new_blocks[-1]
                    if last_block.kind == "paragraph":
                        text_lower = last_block.text.lower()
                        if "consider the following" in text_lower or "consider the following aspects" in text_lower:
                            has_context = True
                
                if not has_context:
                    # Add context paragraph before checklist
                    new_blocks.append(AppleDocBlock(
                        kind="paragraph",
                        text="Consider the following aspects when planning:"
                    ))
                new_blocks.extend(checklist_items)
                new_blocks.extend(other_items)
            else:
                # Not a checklist, keep as-is
                new_blocks.extend(list_items)
        else:
            new_blocks.append(block)
            i += 1
    
    return AppleDocSection(
        heading=section.heading,
        level=section.level,
        blocks=new_blocks
    )


def _detect_semantic_role(text: str) -> Optional[str]:
    """
    Detect semantic role of a paragraph for conceptual_strategy documents.
    This helps identify duplicate content at semantic level, not just text level.
    
    Returns semantic role or None if not identifiable.
    """
    if not text:
        return None
    
    text_lower = text.lower()
    
    # Semantic roles based on content patterns
    if any(word in text_lower for word in ["timeline", "update", "refresh", "reload", "schedule"]):
        if "apns" in text_lower or "push notification" in text_lower:
            return "update_mechanism_push"
        return "update_mechanism"
    
    if any(word in text_lower for word in ["tap", "launch", "deep link", "link", "open"]):
        return "interaction_launch"
    
    if any(word in text_lower for word in ["button", "toggle", "interaction", "app intents"]):
        return "interaction_direct"
    
    if any(word in text_lower for word in ["configurable", "customizable", "select", "choose"]):
        return "configuration"
    
    if any(word in text_lower for word in ["smart stack", "relevance", "ranking", "suggestion"]):
        return "relevance_ranking"
    
    if any(word in text_lower for word in ["privacy", "sensitive", "lock", "always on", "redaction"]):
        return "privacy_visibility"
    
    if any(word in text_lower for word in ["extension", "app group", "shared container", "database"]):
        return "extension_setup"
    
    if any(word in text_lower for word in ["plan", "adoption", "iterative", "start with"]):
        return "adoption_strategy"
    
    return None


def _deduplicate_by_semantic_role(sections: List[AppleDocSection]) -> List[AppleDocSection]:
    """
    Remove duplicate paragraphs based on semantic role, not just exact text match.
    This prevents semantic redundancy (same idea expressed differently) in conceptual_strategy documents.
    """
    result: List[AppleDocSection] = []
    
    for section in sections:
        if section.level != 2:
            result.append(section)
            continue
        
        # Track semantic roles within this H2 section
        seen_roles: dict[str, List[AppleDocBlock]] = {}
        new_blocks: List[AppleDocBlock] = []
        
        for block in section.blocks:
            if block.kind == "paragraph" and block.text:
                role = _detect_semantic_role(block.text)
                
                if role and role in seen_roles:
                    # Check if this is substantially different from existing content
                    # If it's very similar semantically, skip it
                    existing_texts = [b.text.lower() for b in seen_roles[role]]
                    current_text_lower = block.text.lower()
                    
                    # Simple similarity check: if > 70% words overlap, consider it duplicate
                    existing_words = set()
                    for et in existing_texts:
                        existing_words.update(et.split())
                    
                    current_words = set(current_text_lower.split())
                    overlap = len(existing_words & current_words)
                    total_unique = len(existing_words | current_words)
                    
                    if total_unique > 0 and overlap / total_unique > 0.7:
                        # Semantic duplicate, skip
                        continue
                    
                    seen_roles[role].append(block)
                elif role:
                    seen_roles[role] = [block]
                
                new_blocks.append(block)
            else:
                new_blocks.append(block)
        
        new_section = AppleDocSection(
            heading=section.heading,
            level=section.level,
            blocks=new_blocks
        )
        result.append(new_section)
    
    return result


def _is_ui_anchor_paragraph(text: str) -> bool:
    """
    Detect purely visual/UI-anchor sentences that refer to screenshots/tables
    without adding semantic content for RAG.

    Examples:
    \"Similarly, the WidgetFamily.accessoryRectangular widget appears as follows:\"
    \"This table shows the availability for each platform:\"
    \"As shown below, ...\"
    """
    if not text:
        return False
    normalized = " ".join(text.split()).lower()
    patterns = (
        "appears as follows",
        "as shown below",
        "is shown below",
        "this table shows",
        "the following table shows",
        "the table below shows",
        "the following table illustrates",
    )
    return any(p in normalized for p in patterns)


def _extract_param_names_from_swift_signature(code_text: str) -> List[str]:
    """
    Extract parameter names from a Swift function signature.

    Example:
    ```swift
    func tableView(_ tableView: UITableView, trailingSwipeActionsConfigurationForRowAt indexPath: IndexPath) -> UISwipeActionsConfiguration?
    ```
    Returns: ["tableView", "indexPath"]

    Handles:
    - External/internal parameter names: `_ tableView:` → extracts "tableView"
    - Multiple parameters separated by commas
    - Optional parameters with default values
    """
    if not code_text:
        return []
    
    # Find the function signature part (between func name and return type)
    # Look for patterns like: func name(...) -> or func name(...) {
    func_match = re.search(r"func\s+\w+\s*\((.*?)\)\s*(?:->|{)", code_text, re.DOTALL)
    if not func_match:
        return []
    
    params_str = func_match.group(1)
    if not params_str.strip():
        return []
    
    param_names: List[str] = []
    
    # Split by commas, but be careful with nested parentheses/types
    # Simple heuristic: split by comma, then extract the last identifier before colon
    parts = []
    depth = 0
    current = ""
    for char in params_str:
        if char == "(":
            depth += 1
            current += char
        elif char == ")":
            depth -= 1
            current += char
        elif char == "," and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += char
    if current.strip():
        parts.append(current.strip())
    
    for part in parts:
        part = part.strip()
        if not part:
            continue
        
        # Extract parameter name: look for pattern like "label name: Type" or "_ name: Type"
        # The name is the identifier right before the colon
        # Handle external/internal: "_ tableView: UITableView" → "tableView"
        # Handle just internal: "indexPath: IndexPath" → "indexPath"
        match = re.search(r"(?:\w+\s+)?(\w+)\s*:", part)
        if match:
            param_name = match.group(1)
            if param_name not in ("_", "inout", "let", "var"):  # Skip keywords
                param_names.append(param_name)
    
    return param_names


def _find_availability_recursive(obj: Any, depth: int = 0) -> Optional[Dict[str, str]]:
    """Recursively search for availability dict, max depth 5 to avoid infinite loops."""
    if depth > 5:
        return None

    if isinstance(obj, dict):
        # Check if this dict itself is availability (has platform-like keys)
        if "availability" in obj:
            candidate = obj["availability"]
            if isinstance(candidate, dict):
                result = {}
                for k, v in candidate.items():
                    if v:
                        result[k] = str(v).strip()
                if result:
                    return result
            elif isinstance(candidate, list):
                # Handle list format: [{"platform": "iOS", "version": "17.0+"}, ...]
                result = {}
                for item in candidate:
                    if isinstance(item, dict):
                        platform = item.get("platform") or item.get("name")
                        version = item.get("version") or item.get("introduced")
                        if platform and version:
                            result[str(platform)] = str(version).strip()
                if result:
                    return result

        # Also check if this dict directly contains platform keys (iOS, macOS, etc.)
        platform_keys = {"iOS", "iPadOS", "macOS", "watchOS", "tvOS", "visionOS", "Mac Catalyst", "Swift"}
        if any(k in platform_keys for k in obj.keys()):
            result = {}
            for k, v in obj.items():
                if k in platform_keys and v:
                    result[k] = str(v).strip()
            if result:
                return result

        # Recurse into nested dicts
        for value in obj.values():
            found = _find_availability_recursive(value, depth + 1)
            if found:
                return found
    elif isinstance(obj, list):
        for item in obj:
            found = _find_availability_recursive(item, depth + 1)
            if found:
                return found

    return None


def _extract_availability_from_initial_state(initial_state: Optional[Dict[str, Any]]) -> Dict[str, str]:
    """
    Extract platform availability from Apple Docs __INITIAL_STATE__.
    
    Returns a dict like {"iOS": "17.0+", "macOS": "14.0+", "Swift": "5.9+"}.
    
    Apple Docs stores availability in various paths within __INITIAL_STATE__:
    - metadata.availability
    - topicMetadata.availability
    - documentation.metadata.availability
    
    This function tries common paths first, then falls back to recursive search.
    """
    if not initial_state:
        return {}
    
    # Try common paths in __INITIAL_STATE__ first (most efficient)
    paths = [
        ["metadata", "availability"],
        ["topicMetadata", "availability"],
        ["documentation", "metadata", "availability"],
        ["reference", "metadata", "availability"],
        ["topic", "metadata", "availability"],
    ]
    
    for path in paths:
        current = initial_state
        for key in path:
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                current = None
                break
        if isinstance(current, dict):
            # Normalize: ensure all values are strings, filter out empty values
            result = {}
            for k, v in current.items():
                if v:  # Skip None, empty strings, etc.
                    result[k] = str(v).strip()
            if result:
                return result

    # Fallback: recursive search for "availability" key anywhere in the structure
    found = _find_availability_recursive(initial_state)
    return found if found else {}


def _extract_availability_from_html(html: str) -> Dict[str, str]:
    """
    Extract platform availability from HTML body as fallback.
    
    Looks for structured availability data in:
    - JSON-LD script tags
    - data-attributes on elements
    - structured lists with platform names
    
    Returns empty dict if not found (we prefer initial_state as source of truth).
    """
    if not html or not _HAS_LXML:
        return {}
    
    try:
        root = lxml_html.fromstring(html)
    except Exception:  # noqa: BLE001
        return {}
    
    result: Dict[str, str] = {}
    
    # Try JSON-LD script tags
    script_tags = root.xpath("//script[@type='application/ld+json']")
    for script in script_tags:
        try:
            data = json.loads(script.text_content())
            # Recursively search for availability in JSON-LD
            found = _find_availability_recursive(data)
            if found:
                result.update(found)
        except Exception:  # noqa: BLE001
            continue
    
    # Try to find structured availability lists in HTML
    # Look for elements that contain platform names followed by versions
    platform_patterns = [
        r"(iOS|iPadOS|macOS|watchOS|tvOS|visionOS|Mac Catalyst|Swift)\s+([\d.]+(?:\+)?)",
    ]
    
    # Platform name normalization map
    platform_normalize_map = {
        "macos": "macOS",
        "ios": "iOS",
        "ipados": "iPadOS",
        "watchos": "watchOS",
        "tvos": "tvOS",
        "visionos": "visionOS",
        "mac catalyst": "Mac Catalyst",
        "swift": "Swift",
    }
    
    # Search in likely locations: aside elements, metadata sections, etc.
    candidates = root.xpath("//aside | //div[contains(@class, 'metadata')] | //div[contains(@class, 'availability')]")
    for candidate in candidates:
        text = candidate.text_content() or ""
        for pattern in platform_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for platform, version in matches:
                platform_lower = platform.lower()
                platform_normalized = platform_normalize_map.get(platform_lower, platform)
                if platform_normalized not in result:
                    result[platform_normalized] = version
    
    return result


def _normalize_optional_func(code_text: str) -> tuple[str, bool]:
    """
    Normalize Swift function signature: remove 'optional' keyword from ObjC-interop methods.

    Returns:
        (normalized_code, is_optional) tuple.
    
    Example:
    "optional func tableView(...)" → ("func tableView(...)", True)
    """
    if not code_text:
        return code_text, False
    
    # Check if this is an optional func (ObjC interop)
    is_optional = "optional func" in code_text or re.search(r"@objc\s+optional\s+func", code_text)
    
    if is_optional:
        # Remove 'optional ' keyword but keep the rest
        normalized = re.sub(r"\boptional\s+func\b", "func", code_text)
        normalized = re.sub(r"@objc\s+optional\s+func", "@objc func", normalized)
        return normalized, True
    
    return code_text, False


def _is_macro_compiler_signature(code_text: str) -> bool:
    """
    Detect compiler-level macro signatures like
    "@attached(...) macro Model()".

    For RAG we generally want to hide these and instead show the
    user-facing macro syntax (e.g. "@Model").
    """
    if not code_text:
        return False
    # Normalize whitespace for easier matching.
    t = " ".join(code_text.split())
    if " macro " not in t:
        return False
    # Heuristic: presence of @attached (or similar) strongly indicates a
    # compiler signature, not user-facing syntax.
    if "@attached" in t:
        return True
    return False


def _infer_macro_syntax(page: "AppleDocPage") -> str:
    """
    Infer the user-facing syntax for a macro API-ref page.

    Strategy:
    - Derive macro name from the title, e.g. "Model()" → "Model".
    - Search code examples for a line starting with "@Model".
      If found, use that exact line.
    - Fallback: "@<MacroName>".
    """
    base_title = page.title or ""
    # Strip trailing parentheses in titles like "Model()".
    macro_name = base_title.split("(", 1)[0].strip() or base_title.strip()
    if not macro_name:
        # Reasonable generic fallback.
        return "@Model"

    candidate_prefix = f"@{macro_name}"

    for section in page.sections:
        for block in section.blocks:
            if block.kind == "code":
                for line in block.text.splitlines():
                    stripped = line.strip()
                    if stripped.startswith(candidate_prefix):
                        return stripped

    return candidate_prefix


def _paragraph_looks_like_code(text: str) -> bool:
    """
    Detect paragraphs that are actually code (e.g. Apple docs render code as plain text in <p>).
    Such blocks should be emitted as fenced code (```swift) so RAG gets proper structure.

    Heuristics: Swift/API-like patterns at start, or high density of braces/keywords.
    """
    if not text or len(text) < 10:
        return False
    t = text.strip()
    # Clear code starters (often from Apple's "Discussion" examples)
    code_starts = (
        "var body:",
        "Var body:",
        "struct ",
        "func ",
        "extension ",
        "class ",
        "enum ",
        "import ",   # Swift
        "#import ",  # Objective-C
        "// ",
        "// Action",
        "// Status",
        "ControlWidgetButton(",
        "ControlWidgetToggle(",
        "Image(systemName:",
        "Label(",
        "Button(",
    )
    if any(t.startswith(s) for s in code_starts):
        return True
    # Contains code-like structure: braces and Swift keywords
    has_braces = "{" in t and "}" in t
    has_parens = "(" in t and ")" in t
    has_swift_keyword = any(
        kw in t for kw in (" func ", " struct ", " var body", " extension ", " View ", " Control ", " @")
    )
    if (has_braces or has_parens) and has_swift_keyword:
        # Avoid normal prose that mentions "function" or "structure"
        lower = t.lower()
        if lower.startswith(("the ", "this ", "when ", "for ", "by default,", "you can", "use ")):
            return False
        return True
    return False


def _is_noise(text: str) -> bool:
    """
    Heuristic filter for UI/navigation noise that is not useful for RAG.
    
    Any text matching BLACKLIST_PATTERNS is considered noise and filtered out.
    """
    if not text:
        return True
    # Compress whitespace/newline sequences to normalize.
    t = " ".join(text.split())
    if len(t) <= 2:
        return True
    # Blacklist check: any match => FAIL.
    return any(pattern in t for pattern in BLACKLIST_PATTERNS)


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
    try:
        all_elements.sort(key=lambda el: el.getroottree().getpath(el))
    except Exception:  # noqa: BLE001
        # Fallback: keep original order if sorting fails
        pass

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

