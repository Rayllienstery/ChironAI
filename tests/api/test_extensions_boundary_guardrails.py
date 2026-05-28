from __future__ import annotations

from pathlib import Path


def test_api_routes_use_extension_service_accessor_not_legacy_flask_keys() -> None:
    root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    for path in (root / "api").rglob("*.py"):
        if path.name == "extensions_service_access.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "llm_extensions_service" in text or "llm_interactor_runtime" in text or "llm_provider_registry" in text:
            offenders.append(str(path.relative_to(root)))

    assert offenders == []


def test_api_routes_do_not_scan_bundled_extension_directories() -> None:
    root = Path(__file__).resolve().parents[2]
    forbidden_patterns = (
        "extensions/bundled",
        "extensions\\bundled",
        '"extensions" / "bundled"',
        "'extensions' / 'bundled'",
        '.joinpath("extensions", "bundled")',
        ".joinpath('extensions', 'bundled')",
    )
    offenders: list[str] = []
    for path in (root / "api").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in forbidden_patterns):
            offenders.append(str(path.relative_to(root)))

    assert offenders == []
