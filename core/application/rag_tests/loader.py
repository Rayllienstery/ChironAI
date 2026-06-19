"""
Load and parse RAG test definitions from Markdown files under rag_tests/.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any


# Default root for tests (project root / rag_tests)
def _get_rag_tests_root() -> Path:
    root = os.environ.get("RAG_TESTS_ROOT")
    if root:
        return Path(root)
    # Assume we are in application/rag_tests; project root is two levels up
    this_file = Path(__file__).resolve()
    return this_file.parent.parent.parent / "rag_tests"


def get_rag_tests_root() -> Path:
    """Return the directory containing rag_tests (or RAG_TESTS_ROOT)."""
    return _get_rag_tests_root()


def parse_test_md(content: str, _source_path: str = "") -> dict[str, Any]:
    """
    Parse a single test Markdown string.
    Returns dict with: name, question, expected_concepts, platform, framework,
    min_os, difficulty, concept_mode, rag_requirement (bool), notes.
    """
    out: dict[str, Any] = {
        "name": "",
        "question": "",
        "expected_concepts": [],
        "concept_groups": [],
        "platform": "",
        "framework": "",
        "min_os": "",
        "difficulty": "intermediate",
        "concept_mode": "all",
        "rag_requirement": True,
        "rag_strict": False,
        "notes": "",
    }
    if not content or not content.strip():
        return out

    # Split by ## headers
    parts = re.split(r"\n##\s+", content.strip(), flags=re.IGNORECASE)
    first = (parts[0] or "").strip()
    rest = {p.split("\n", 1)[0].strip().lower().replace(" ", "_"): p.split("\n", 1)[-1] if "\n" in p else "" for p in (parts[1:] or [])}

    # First block: title (# Test Name) and key: value metadata
    lines = first.split("\n")
    title_line = None
    meta_lines: list[str] = []
    for line in lines:
        if line.startswith("# "):
            title_line = line[2:].strip()
        else:
            meta_lines.append(line)

    if title_line:
        out["name"] = title_line

    rag_required_override: bool | None = None

    # Parse key: value in first block
    for line in meta_lines:
        if ":" in line:
            key, _, value = line.partition(":")
            key = key.strip().lower().replace(" ", "_")
            value = value.strip()
            if key == "platform":
                out["platform"] = value
            elif key == "framework":
                out["framework"] = value
            elif key == "minos" or key == "min_os":
                out["min_os"] = value
            elif key == "difficulty":
                out["difficulty"] = value or "intermediate"
            elif key == "concept_mode":
                out["concept_mode"] = (value or "all").strip().lower()
                if out["concept_mode"] not in ("any", "all"):
                    out["concept_mode"] = "all"
            elif key in ("rag_strict", "strict_rag"):
                out["rag_strict"] = (value or "").strip().lower() in ("true", "yes", "1")
            elif key in ("rag_required", "require_rag"):
                rag_required_override = (value or "").strip().lower() not in ("no", "false", "0", "off")
            else:
                pass  # ignore unknown

    # Sections
    def section(name: str) -> str:
        key = name.lower().replace(" ", "_")
        return (rest.get(key) or "").strip()

    out["question"] = section("Question")
    out["notes"] = section("Notes")

    concepts_text = section("Expected Concepts")
    if concepts_text:
        out["expected_concepts"] = [
            line.strip().lstrip("-").strip()
            for line in concepts_text.split("\n")
            if line.strip()
        ]

    cg_text = section("Concept Groups")
    concept_groups: list[list[str]] = []
    if cg_text:
        for raw in cg_text.split("\n"):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "||" in line:
                parts = [p.strip() for p in line.split("||")]
                parts = [p for p in parts if p]
                if parts:
                    concept_groups.append(parts)
    if concept_groups:
        out["concept_groups"] = concept_groups

    rag_text = section("RAG Requirement")
    if rag_required_override is not None:
        out["rag_requirement"] = rag_required_override
    else:
        # Legacy: non-empty RAG section implied "require RAG narrative"; empty => default True
        out["rag_requirement"] = bool(rag_text) if rag_text.strip() else True

    return out


def _relative_path(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.name


def load_test(root: Path, file_path: Path) -> dict[str, Any] | None:
    """Load a single test from a .md file. Returns None if unreadable."""
    if file_path.suffix.lower() != ".md":
        return None
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return None
    data = parse_test_md(content, str(file_path))
    data["id"] = _relative_path(root, file_path).replace(".md", "").replace("/", "_").replace("\\", "_")
    data["file_path"] = _relative_path(root, file_path)
    data["absolute_path"] = str(file_path)
    return data


def load_all_tests(root: Path | None = None) -> list[dict[str, Any]]:
    """
    Discover all .md files under rag_tests (or root) and parse them.
    Returns list of test dicts with id, name, question, expected_concepts, platform, framework, etc.
    """
    if root is None:
        root = get_rag_tests_root()
    root = Path(root)
    if not root.is_dir():
        return []

    tests: list[dict[str, Any]] = []
    for path in root.rglob("*.md"):
        # Skip hidden files and documentation-only files like README.md
        if path.name.startswith("."):
            continue
        if path.name.lower() == "readme.md":
            continue
        data = load_test(root, path)
        if data and data.get("question"):
            tests.append(data)
    return tests


def list_test_filters(tests: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Return distinct platform, framework, difficulty for filter dropdowns."""
    platforms: set[str] = set()
    frameworks: set[str] = set()
    difficulties: set[str] = set()
    for t in tests:
        if t.get("platform"):
            platforms.add(t["platform"])
        if t.get("framework"):
            frameworks.add(t["framework"])
        if t.get("difficulty"):
            difficulties.add(t["difficulty"])
    return {
        "platform": sorted(platforms),
        "framework": sorted(frameworks),
        "difficulty": sorted(difficulties),
    }
