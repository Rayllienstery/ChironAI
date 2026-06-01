"""
Domain-level metadata inference for indexed chunks.

Pure business logic for:
- Extracting iOS and Swift version markers from chunk text.
- Inferring high-level metadata (language, technology, domain, product, doc_type)
  from source_id, filename, url, section_path.

Stable keys (string values only). Heuristics are conservative; extend for new
sources without changing callers.
"""

from __future__ import annotations

import re


_IOS_VERSION_RE = re.compile(r"\biOS\s+(\d+(?:\.\d+)*)\+?", re.IGNORECASE)
_SWIFT_VERSION_RE = re.compile(r"\bSwift\s+(\d+(?:\.\d+)*)", re.IGNORECASE)


def extract_versions(text: str) -> tuple[list[str], list[str]]:
    """
    Extract iOS and Swift version markers from a chunk of text.
    Returns (ios_versions, swift_versions) as sorted unique strings.
    """
    ios = {m.group(1) for m in _IOS_VERSION_RE.finditer(text or "")}
    swift = {m.group(1) for m in _SWIFT_VERSION_RE.finditer(text or "")}
    return sorted(ios), sorted(swift)


def infer_metadata(
    source_id: str,
    filename: str,
    url: str | None,
    section_path: list[str],
    text: str,
) -> dict[str, str]:
    """
    Infer high-level metadata for a chunk in a stable, extensible way.

    Stable keys (string values only):
    - language: swift / objc / rust / js / ts / shell / dockerfile / unknown
    - technology: swiftui / uikit / foundation / concurrency / ... / unknown
    - domain: framework_guide / api_ref / language_guide / app_store / tooling / ...
    - product: ios / ipados / macos / tvos / watchos / visionos / server / tooling / unknown
    - doc_type: documentation / howto / sample_code / policy / legal / marketing / help_center
    - doc_scope: api_symbol / guide / tutorial / discussion (and future: articles, books, forums)

    Heuristics are intentionally conservative.
    """
    language = "unknown"
    technology = "unknown"
    domain = "documentation"
    product = "unknown"
    doc_type = "documentation"
    doc_scope = ""

    lower_name = (filename or "").lower()
    lower_url = (url or "").lower()

    if source_id == "apple_documentation":
        language = "swift"
        domain = "framework_guide"
        product = "ios"
        if "/documentation/swift" in lower_url:
            technology = "swift"
            domain = "language_guide"
        elif "/documentation/uikit" in lower_url:
            technology = "uikit"
        elif "/documentation/swiftui" in lower_url:
            technology = "swiftui"
        elif "/documentation/combine" in lower_url:
            technology = "combine"
        elif "/documentation/swiftdata" in lower_url:
            technology = "swiftdata"
        elif "/documentation/foundation" in lower_url:
            technology = "foundation"
        elif "/documentation/widgetkit" in lower_url:
            technology = "widgetkit"
        elif "/documentation/coredata" in lower_url:
            technology = "coredata"
        elif "/documentation/quartzcore" in lower_url:
            technology = "core_animation"
        elif "/documentation/avfoundation" in lower_url:
            technology = "avfoundation"
        elif "/documentation/mapkit" in lower_url:
            technology = "mapkit"
        elif "/documentation/coregraphics" in lower_url:
            technology = "coregraphics"
        elif "/documentation/storekit" in lower_url:
            technology = "storekit"
            domain = "app_store"
        elif "/documentation/xcode" in lower_url:
            technology = "xcode"
            domain = "tooling"
            product = "tooling"
        else:
            technology = "foundation"
    elif source_id == "swift_book":
        language = "swift"
        technology = "swift"
        domain = "language_guide"
        doc_scope = "guide"
    elif source_id == "swift_docs":
        language = "swift"
        domain = "language_guide"
    elif source_id == "swift_whats_new":
        language = "swift"
        technology = "swift"
        domain = "language_guide"
        product = "ios"
        doc_type = "release_notes"
    elif source_id == "swiftui_whats_new":
        language = "swift"
        technology = "swiftui"
        domain = "framework_guide"
        product = "ios"
        doc_type = "release_notes"
    elif source_id == "ios_whats_new":
        language = "swift"
        technology = "uikit"
        domain = "framework_guide"
        product = "ios"
        doc_type = "release_notes"
    elif source_id in {
        "apple_uikit",
        "swiftui_docs",
        "combine_docs",
        "swiftdata_docs",
        "foundation_docs",
        "coredata_docs",
        "coreanimation_docs",
        "avfoundation_docs",
        "mapkit_docs",
        "coregraphics_docs",
        "storekit_docs",
    }:
        language = "swift"
        domain = "framework_guide"
        product = "ios"
        if source_id == "apple_uikit":
            technology = "uikit"
        elif source_id == "swiftui_docs":
            technology = "swiftui"
        elif source_id == "combine_docs":
            technology = "combine"
        elif source_id == "swiftdata_docs":
            technology = "swiftdata"
        elif source_id == "foundation_docs":
            technology = "foundation"
        elif source_id == "coredata_docs":
            technology = "coredata"
        elif source_id == "coreanimation_docs":
            technology = "core_animation"
        elif source_id == "avfoundation_docs":
            technology = "avfoundation"
        elif source_id == "mapkit_docs":
            technology = "mapkit"
        elif source_id == "coregraphics_docs":
            technology = "coregraphics"
        elif source_id == "storekit_docs":
            technology = "storekit"
            domain = "app_store"
    elif source_id.startswith("wwdc_sessions_"):
        language = "swift"
        technology = "wwdc_sessions"
        domain = "framework_guide"
    elif source_id == "xcode_docs":
        language = "swift"
        technology = "xcode"
        domain = "tooling"
        product = "tooling"
    elif source_id == "swift_org_docs":
        language = "swift"
        domain = "language_guide"
    elif source_id in {
        "hws_swift",
        "swiftbysundell_articles",
        "kodeco_ios",
        "objc_io_issues",
        "nshipster_articles",
        "pointfree_collections",
    }:
        language = "swift"
        domain = "community_guide"
        doc_type = "howto"
    elif source_id in {"firebase_ios", "stripe_ios"}:
        language = "swift"
        domain = "tooling"
        product = "ios"
    elif source_id.startswith("pf_"):
        language = "swift"
        domain = "framework_guide"
        product = "ios"
        if source_id == "pf_tca":
            technology = "tca"
        elif source_id == "pf_dependencies":
            technology = "dependencies"
        elif source_id == "pf_navigation":
            technology = "navigation"
        elif source_id == "pf_sharing":
            technology = "sharing"
        elif source_id == "pf_snapshot_testing":
            technology = "snapshot_testing"
            domain = "tooling"
        elif source_id == "pf_identified_collections":
            technology = "identified_collections"
        elif source_id == "pf_clocks":
            technology = "clocks"
            domain = "tooling"
    elif source_id.startswith("gh_"):
        language = "swift"
        domain = "framework_guide"
        product = "ios"
        if source_id == "gh_alamofire":
            technology = "networking"
        elif source_id == "gh_moya":
            technology = "networking"
        elif source_id in {"gh_kingfisher", "gh_sdwebimage"}:
            technology = "image_loading"
        elif source_id == "gh_snapkit":
            technology = "layout"
        elif source_id == "gh_swiftlint":
            technology = "linting"
            domain = "tooling"
        elif source_id == "gh_realm_swift":
            technology = "persistence"
        elif source_id == "gh_rxswift":
            technology = "reactive"
        elif source_id == "gh_combineext":
            technology = "combine"
        elif source_id in {"gh_quick", "gh_nimble"}:
            technology = "testing"
            domain = "tooling"
    elif source_id == "rust_docs":
        language = "rust"
        domain = "language_guide"
        product = "server"
    elif source_id == "node_docs":
        language = "js"
        technology = "nodejs"
        domain = "framework_guide"
        product = "server"

    if "swiftui" in lower_name:
        technology = "swiftui"
        domain = "framework_guide"
        if product == "unknown":
            product = "ios"
    if "uikit" in lower_name:
        technology = "uikit"
        domain = "framework_guide"
        if product == "unknown":
            product = "ios"
    if "combine" in lower_name:
        technology = "combine"
        domain = "framework_guide"
    if "concurrency" in lower_name or "actors" in lower_name:
        technology = "concurrency"
        domain = "language_guide"
    if "distributed" in lower_name:
        technology = "distributed"
        if domain == "documentation":
            domain = "language_guide"
    if "foundation" in lower_name and technology == "unknown":
        technology = "foundation"
        domain = "framework_guide"
    if any(k in lower_name for k in ("storekit", "in-app-purchase", "in_app_purchase")):
        technology = "storekit"
        domain = "app_store"
        product = "ios"
    if "testflight" in lower_name:
        domain = "app_store"
        product = "ios"
    if "app-store" in lower_name or "appstore" in lower_name:
        domain = "app_store"
        if product == "unknown":
            product = "ios"
    if "xcode" in lower_name and technology == "unknown":
        technology = "xcode"
        domain = "tooling"
        product = "tooling"
    if "playgrounds" in lower_name:
        technology = "swift_playgrounds"
        domain = "tooling"
        product = "tooling"
    if any(k in lower_name for k in ("sample", "example", "snippet")):
        doc_type = "sample_code"
    if any(k in lower_name for k in ("how-to", "howto", "guide")) and doc_type == "documentation":
        doc_type = "howto"
    if any(k in lower_name for k in ("policy", "policies", "guidelines", "review")):
        domain = "policy"
        doc_type = "policy"
    if any(k in lower_name for k in ("terms", "agreement", "license", "licence")):
        doc_type = "legal"

    if "/documentation/swift/" in lower_url:
        language = "swift"
        domain = "language_guide"
    if "/documentation/uikit" in lower_url:
        technology = "uikit"
        domain = "framework_guide"
        if product == "unknown":
            product = "ios"
    if "/documentation/swiftui" in lower_url:
        technology = "swiftui"
        domain = "framework_guide"
        if product == "unknown":
            product = "ios"
    if "/documentation/foundation" in lower_url and technology == "unknown":
        technology = "foundation"
        domain = "framework_guide"
    if "/documentation/storekit" in lower_url:
        technology = "storekit"
        domain = "app_store"
        product = "ios"
    if "testflight" in lower_url:
        domain = "app_store"
        product = "ios"
    if "app-store" in lower_url or "/app-store/" in lower_url or "/appstore/" in lower_url:
        domain = "app_store"
        if product == "unknown":
            product = "ios"
    if "/xcode/" in lower_url or "/xcode-playgrounds" in lower_url:
        technology = "xcode"
        domain = "tooling"
        product = "tooling"

    if section_path:
        root = (section_path[0] or "").lower()
        if "swift playgrounds" in root:
            technology = "swift_playgrounds"
            domain = "tooling"
            product = "tooling"
        if "testflight" in root:
            domain = "app_store"
            product = "ios"
        if "app store" in root or "appstore" in root:
            domain = "app_store"
            if product == "unknown":
                product = "ios"

    # Infer doc_scope for retrieval (source type: api_symbol, guide, tutorial, discussion).
    if not doc_scope:
        if "/documentation/" in lower_url and section_path:
            first = (section_path[0] or "").strip()
            if first and ("(" in first or ")" in first or first in ("init", "deinit")):
                doc_scope = "api_symbol"
        if not doc_scope and section_path and source_id == "apple_documentation":
            doc_scope = _doc_scope_from_section_path(section_path)
        if not doc_scope and any(k in lower_url for k in ("guide", "guides", "overview")):
            doc_scope = "guide"
        if not doc_scope and any(k in lower_url for k in ("tutorial", "tutorials", "getting-started", "getting_started")):
            doc_scope = "tutorial"
        if not doc_scope and any(k in lower_name for k in ("guide", "guides", "overview")):
            doc_scope = doc_scope or "guide"
        if not doc_scope and any(k in lower_name for k in ("tutorial", "tutorials", "getting-started")):
            doc_scope = doc_scope or "tutorial"

    return {
        "language": language,
        "technology": technology,
        "domain": domain,
        "product": product,
        "doc_type": doc_type,
        "doc_scope": doc_scope,
    }


# Normalize Apple doc section headings to stable slugs for filtering (e.g. "Return Value" -> "return_value").
_SECTION_NORMALIZE: dict[str, str] = {
    "return value": "return_value",
    "return values": "return_value",
    "discussion": "discussion",
    "parameters": "parameters",
    "parameter": "parameters",
    "overview": "overview",
    "syntax": "syntax",
    "example": "example",
    "examples": "example",
    "description": "description",
    "declaration": "declaration",
    "see also": "see_also",
    "topics": "topics",
}

_DOC_SCOPE_API_SECTIONS = frozenset(
    {
        "discussion",
        "return_value",
        "parameters",
        "syntax",
        "example",
        "declaration",
        "description",
    }
)
_DOC_SCOPE_GUIDE_SECTIONS = frozenset({"overview", "see_also", "topics"})


def _section_slug(raw: str) -> str:
    key = (raw or "").lower().strip()
    return _SECTION_NORMALIZE.get(key, key.replace(" ", "_"))


def _doc_scope_from_section_path(section_path: list[str]) -> str:
    """Map Apple doc section headings to doc_scope for retrieval weighting."""
    if not section_path:
        return ""
    slugs = [_section_slug(part) for part in section_path if (part or "").strip()]
    if not slugs:
        return ""
    if any(s in _DOC_SCOPE_API_SECTIONS for s in slugs):
        return "api_symbol"
    if any(s in _DOC_SCOPE_GUIDE_SECTIONS for s in slugs):
        return "guide"
    return ""


def _apple_doc_scope_from_doc_kind(doc_kind: str | None) -> str:
    kind = (doc_kind or "").strip().lower()
    if kind in {"api_ref", "api_ref_macro"}:
        return "api_symbol"
    if kind in {"conceptual", "conceptual_strategy", "overview"}:
        return "guide"
    return ""


from rag_service.config import get_indexing_int

# Optimal prefix length 40-80 chars to improve retrieval without noisy embedding.
EMBED_PREFIX_MAX_CHARS: int = get_indexing_int("embed_prefix_max_chars", 80)


def estimate_token_count(text: str) -> int:
    """
    Approximate token count for context assembly and chunk balancing.
    Uses word count * 1.3 (typical for English); document as approximate.
    """
    if not text or not text.strip():
        return 0
    words = len((text or "").split())
    return max(1, int(words * 1.3))


def build_embed_prefix(page_meta: dict[str, str] | None, section_path: list[str]) -> str:
    """
    Build a short semantic prefix for embedding (40-80 chars) to improve retrieval.
    Format: "Framework API / Function: symbol / Section: section". No long sentences.
    Used only at embed time; payload stores original text.
    """
    if not page_meta:
        page_meta = {}
    parts: list[str] = []
    framework = (page_meta.get("framework") or "").strip()
    if framework:
        # Short label only; avoid full framework description.
        parts.append(f"{framework} API" if "API" not in framework else framework)
    display = infer_chunk_display_meta(section_path)
    symbol = display.get("symbol") or ""
    section = display.get("section") or ""
    if symbol:
        parts.append(f"Function: {symbol}")
    if section:
        parts.append(f"Section: {section}")
    prefix = " / ".join(parts)
    max_chars = EMBED_PREFIX_MAX_CHARS
    if len(prefix) > max_chars:
        prefix = prefix[: max_chars - 3].rstrip()
        # Cut at last space to avoid mid-word.
        last_sp = prefix.rfind(" ")
        if last_sp > max_chars // 2:
            prefix = prefix[:last_sp]
        prefix = prefix.rstrip(" /")
    return (prefix + " ") if prefix else ""


def infer_chunk_display_meta(section_path: list[str]) -> dict[str, str]:
    """
    Infer optional symbol and section for a chunk from its section_path.
    Used for payload fields: symbol (e.g. "mapValues(_:)") and section (e.g. "parameters").
    Returns dict with optional "symbol" and "section" keys (only set when applicable).
    """
    result: dict[str, str] = {}
    if not section_path:
        return result
    first = (section_path[0] or "").strip()
    if first and ("(" in first or ")" in first or first in ("init", "deinit")):
        result["symbol"] = first
    elif first and " " not in first and first[0].isupper() and len(first) >= 3:
        # Type/symbol page title (e.g. NavigationStack, UIApplication).
        result["symbol"] = first
    last = (section_path[-1] or "").strip() if section_path else ""
    if last:
        key = last.lower().strip()
        result["section"] = _SECTION_NORMALIZE.get(key, key.replace(" ", "_"))
    return result


__all__ = [
    "extract_versions",
    "infer_metadata",
    "infer_chunk_display_meta",
    "build_embed_prefix",
    "estimate_token_count",
]
