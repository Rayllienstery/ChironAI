from rag_service.infrastructure.cli_runner import OllamaInteractorCliError
from rag_service.infrastructure.ollama_chat import _chat_runtime_error


def test_chat_runtime_error_prefers_502_over_false_405_match() -> None:
    exc = OllamaInteractorCliError(
        '502 Server Error: Bad Gateway for url: http://localhost:11434/api/chat - '
        'Ollama: Post "https://ollama.com:443/api/chat?ts=1776597373": wsarecv closed',
        stderr="",
    )
    err = _chat_runtime_error("glm-5.1:cloud", "http://localhost:11434/api/chat", exc)
    msg = str(err)
    assert "HTTP 502" in msg
    assert "method not allowed (405)" not in msg


def test_chat_runtime_error_uses_structured_status_code_from_stderr() -> None:
    exc = OllamaInteractorCliError(
        "request failed",
        stderr='{"error":"request failed","body":{"status_code":404,"error":"not found"}}',
    )
    err = _chat_runtime_error("llama3", "http://localhost:11434/api/chat", exc)
    assert "not found (404)" in str(err)

