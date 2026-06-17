from __future__ import annotations

from pathlib import Path


def test_legacy_extension_service_flask_key_is_removed() -> None:
    root = Path(__file__).resolve().parents[2]
    legacy_key = "llm_" + "extensions_service"
    offenders: list[str] = []
    for base in ("Core/api", "CoreModules", "Core/modules", "Core/core"):
        for path in (root / base).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if legacy_key in text:
                offenders.append(path.relative_to(root).as_posix())

    assert offenders == []


def test_extension_runtime_flask_keys_are_confined_to_contract_accessors() -> None:
    root = Path(__file__).resolve().parents[2]
    allowed = {
        "Core/api/http/extensions_service_access.py",
        "Core/core/contracts/extensions_api.py",
    }
    forbidden = ("llm_interactor_runtime", "llm_provider_registry")
    offenders: list[str] = []
    for base in ("Core/api", "CoreModules", "Core/modules", "Core/core"):
        for path in (root / base).rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            text = path.read_text(encoding="utf-8")
            if rel not in allowed and any(token in text for token in forbidden):
                offenders.append(rel)

    assert offenders == []


def test_api_routes_use_extension_service_accessor_not_legacy_flask_keys() -> None:
    root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    legacy_key = "llm_" + "extensions_service"
    for path in (root / "Core" / "api").rglob("*.py"):
        if path.name == "extensions_service_access.py":
            continue
        text = path.read_text(encoding="utf-8")
        if legacy_key in text or "llm_interactor_runtime" in text or "llm_provider_registry" in text:
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
    for path in (root / "Core" / "api").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if any(pattern in text for pattern in forbidden_patterns):
            offenders.append(str(path.relative_to(root)))

    assert offenders == []


def test_crawler_routes_do_not_import_rag_tests_routes() -> None:
    root = Path(__file__).resolve().parents[2]
    offenders: list[str] = []
    crawler_dir = root / "Core" / "api" / "http"
    for path in crawler_dir.glob("webui_crawler*.py"):
        text = path.read_text(encoding="utf-8")
        if "rag_tests_routes" in text:
            offenders.append(path.relative_to(root).as_posix())

    assert offenders == []
    root = Path(__file__).resolve().parents[2]
    allowed_prefixes = (
        "Core/modules/extensions_backend/",
        "CoreModules/ExtensionsHost/",
    )
    forbidden_tokens = (
        "from extensions_backend",
        "import extensions_backend",
    )
    offenders: list[str] = []
    for base in ("Core/api", "Core/application", "Core/core", "Core/infrastructure", "Core/modules", "CoreModules"):
        scan_root = root / base
        if not scan_root.is_dir():
            continue
        for path in scan_root.rglob("*.py"):
            rel = path.relative_to(root).as_posix()
            if rel.startswith(allowed_prefixes):
                continue
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in forbidden_tokens):
                offenders.append(rel)

    assert offenders == []
