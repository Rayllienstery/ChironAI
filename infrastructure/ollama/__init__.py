"""
Ollama-based infrastructure adapters.

Provides concrete implementations of domain ports for:
- EmbeddingProvider via /api/embed
- ChatLLMClient via /api/chat
"""

from infrastructure.ollama.chat_client import OllamaChatClient
from infrastructure.ollama.embed_client import OllamaEmbeddingProvider
from infrastructure.ollama.rerank_client import OllamaRerankClient

__all__ = ["OllamaChatClient", "OllamaEmbeddingProvider", "OllamaRerankClient"]
