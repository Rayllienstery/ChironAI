"""Metadata, availability, and signature helpers for Apple docs extraction."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional

from webui_backend.apple_docs_html import _HAS_LXML, lxml_html
from webui_backend.apple_docs_models import AppleDocPage
from webui_backend.apple_docs_text import BLACKLIST_PATTERNS


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
        if any(k in platform_keys for k in obj):
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
    return "@attached" in t


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
        return not lower.startswith(("the ", "this ", "when ", "for ", "by default,", "you can", "use "))
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


