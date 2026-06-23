"""Utilities for reading the project changelog."""

from __future__ import annotations

from pathlib import Path


def get_latest_changelog_content(project_root: Path) -> str:
    """
    Read CHANGELOG.md and return the content of the latest version section.
    """
    changelog_path = project_root / "CHANGELOG.md"
    if not changelog_path.is_file():
        return ""

    try:
        with changelog_path.open("r", encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return ""

    content: list[str] = []
    found_first_version = False
    
    for line in lines:
        # Look for the first version header like ## [0.4.1] - 2026-05-22
        if line.startswith("## ["):
            if found_first_version:
                # We reached the next version, stop here
                break
            found_first_version = True
            continue
        
        if found_first_version:
            content.append(line)

    return "".join(content).strip()
