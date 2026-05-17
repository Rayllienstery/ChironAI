from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

ALLOWED_INFRASTRUCTURE_OLLAMA_IMPORT_FILES = {
    "api/http/webui_routes.py",
    "CoreModules/LlmProxy/llm_proxy/chat_completions_gemini_native.py",
    "CoreModules/LlmProxy/llm_proxy/chat_completions_handler.py",
    "CoreModules/LlmProxy/llm_proxy/chat_completions_messages.py",
    "CoreModules/LlmProxy/llm_proxy/chat_completions_ollama_proxy.py",
    "infrastructure/ollama/__init__.py",
    "infrastructure/ollama/chat_client.py",
    "infrastructure/ollama/embed_client.py",
    "infrastructure/ollama/rerank_client.py",
    "tests/api/test_http_endpoints.py",
    "tests/application/test_compat_wrappers.py",
    "tests/infrastructure/test_ollama_chat_client_stream_merge.py",
    "tests/infrastructure/test_ollama_cli_runner.py",
    "tests/llm_proxy/test_openai_ollama_tool_bridge.py",
}

IMPORT_RE = re.compile(r"^\s*(?:from\s+infrastructure\.ollama\b|import\s+infrastructure\.ollama\b)", re.MULTILINE)


def _python_files() -> list[Path]:
    roots = ["api", "application", "CoreModules", "infrastructure", "extensions", "tests"]
    out: list[Path] = []
    for root in roots:
        out.extend((ROOT / root).rglob("*.py"))
    return out


def test_no_new_direct_infrastructure_ollama_imports_without_allowlist() -> None:
    offenders: list[str] = []
    for path in _python_files():
        rel = path.relative_to(ROOT).as_posix()
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = path.read_text(encoding="utf-8-sig")
        if IMPORT_RE.search(text) and rel not in ALLOWED_INFRASTRUCTURE_OLLAMA_IMPORT_FILES:
            offenders.append(rel)

    assert offenders == []

