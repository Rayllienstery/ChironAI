"""Scope markers, checklist enhancement, and semantic deduplication for Apple docs."""

from __future__ import annotations

from typing import List, Optional

from webui_backend.apple_docs_models import AppleDocBlock, AppleDocSection


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
            scope_labels = {
                "widgets and live activities": "Widgets and Live Activities",
                "live activities": "Live Activities",
                "controls": None,
                "widget extension setup": "Widgets",
                "smart stacks": "Smart Stacks",
                "privacy and visibility": "Widgets",
                "planning adoption": None,
            }
            return scope_labels.get(scope)
    
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


