"""Derive Ollama HTTP base from /api/chat URL."""


def ollama_api_base_from_chat_url(chat_url: str) -> str:
    u = (chat_url or "").rstrip("/")
    if u.endswith("/api/chat"):
        return u[: -len("/api/chat")]
    return u


__all__ = ["ollama_api_base_from_chat_url"]
