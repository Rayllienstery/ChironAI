"""Data models for extracted Apple Developer documentation pages."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
