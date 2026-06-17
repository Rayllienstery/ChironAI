from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

IMPORT_RE = re.compile(r"^\s*(?:from\s+infrastructure\.ollama\b|import\s+infrastructure\.ollama\b)", re.MULTILINE)
CORE_OLLAMA_HTTP_RE = re.compile(r"(localhost:11434|OLLAMA_EMBED_URL|ollama_upstream|completions_generate)")


def _python_files() -> list[Path]:
    roots = ["Core/api", "Core/application", "CoreModules", "Core/infrastructure", "extensions", "tests"]
    out: list[Path] = []
    for root in roots:
        out.extend((ROOT / root).rglob("*.py"))
    return out


def test_no_direct_infrastructure_ollama_imports() -> None:
    offenders: list[str] = []
    for path in _python_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8-sig")
        if IMPORT_RE.search(text):
            offenders.append(rel)

    assert offenders == []


def test_core_no_direct_ollama_http_ownership() -> None:
    allowed_prefixes = (
        "Core/config/",
        "extensions/bundled/ollama-provider/",
        "tests/",
        "CoreModules/OllamaInteractor/",
        "CoreModules/RagService/rag_service/config.py",
    )
    offenders: list[str] = []
    for root in [
        "Core/api",
        "Core/application",
        "CoreModules/LlmProxy",
        "Core/modules/webui_backend",
        "Core/domain",
        "Core/infrastructure",
    ]:
        for path in (ROOT / root).rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".py", ".md", ".yaml", ".yml"}:
                continue
            rel = path.relative_to(ROOT).as_posix()
            if rel.startswith(allowed_prefixes):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if CORE_OLLAMA_HTTP_RE.search(text):
                offenders.append(rel)

    assert offenders == []
