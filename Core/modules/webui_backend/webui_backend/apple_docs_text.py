"""Text normalization and filtering heuristics for Apple docs extraction."""

from __future__ import annotations

import re
from typing import Optional

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
    # Filter ALL such paragraphs — they're references, not content.
    # No length limit: even long ones like "For more information, refer to Preparing widgets..."
    # should be filtered as they create false retrieval anchors.
    return "http://" not in normalized and "https://" not in normalized


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
    return bool("use widgetkit to build" in lower and "becomes part of the widget ecosystem" in lower)


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


