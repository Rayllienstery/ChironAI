"""Guards for rag_service standalone isolation."""

from __future__ import annotations

from pathlib import Path

RAG_SERVICE_ROOT = Path(__file__).resolve().parents[2] / "CoreModules" / "RagService" / "rag_service"
FORBIDDEN_IMPORT_SNIPPETS = (
    "from application.",
    "import application.",
    "from domain.",
    "import domain.",
    "from infrastructure.",
    "import infrastructure.",
    "from config ",
    "from config.",
    "import config",
)


def test_rag_service_has_no_monorepo_runtime_imports() -> None:
    offenders: list[str] = []
    for path in RAG_SERVICE_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if not (stripped.startswith("from ") or stripped.startswith("import ")):
                continue
            for snippet in FORBIDDEN_IMPORT_SNIPPETS:
                if snippet in stripped:
                    offenders.append(f"{path.relative_to(RAG_SERVICE_ROOT)} -> {stripped}")
    assert offenders == []
