from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

IMPORT_RE = re.compile(r"^\s*(?:from\s+infrastructure\.ollama\b|import\s+infrastructure\.ollama\b)", re.MULTILINE)
CHECKBOX_RE = re.compile(r"^\s*-\s\[[ x]\]\s+\S")
CORE_OLLAMA_HTTP_RE = re.compile(r"(localhost:11434|OLLAMA_EMBED_URL|ollama_upstream|completions_generate)")


def _python_files() -> list[Path]:
    roots = ["api", "application", "CoreModules", "infrastructure", "extensions", "tests"]
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
        "config/",
        "extensions/bundled/ollama-provider/",
        "tests/",
        "CoreModules/OllamaInteractor/",
        "CoreModules/RagService/rag_service/config.py",
    )
    offenders: list[str] = []
    for root in ["api", "application", "CoreModules/LlmProxy", "CoreModules/WebUIBackend", "domain", "infrastructure"]:
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


def test_ollama_migration_todo_remains_decision_complete() -> None:
    path = ROOT / "OLLAMA_EXTENSION_MIGRATION_TODO.md"
    text = path.read_text(encoding="utf-8")

    assert path.is_file()
    assert not re.search(r"[А-Яа-яЁё]", text)
    for line in text.splitlines():
        if "- [" in line:
            assert CHECKBOX_RE.match(line), line

    required_phrases = [
        "decision-complete migration guide",
        "`ollama-provider` owns Ollama behavior",
        "provider-generic",
        "Do not make CoreUI know Ollama internals",
        "host_context.docker_runtime",
        "DockerContainerSpec",
        "Do not move Qdrant",
        "Do not add new core direct-Ollama HTTP ownership",
        "Core no longer exposes raw Ollama-compatible routes",
        "Manual Smoke Checklist",
        "Suggested Regression Searches",
        "Acceptance Criteria",
    ]
    for phrase in required_phrases:
        assert phrase in text
