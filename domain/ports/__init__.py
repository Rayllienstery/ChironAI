"""
Domain ports (interfaces).

Define abstract protocols for repositories and external services such as:
- RagRepository (Qdrant access)
- EmbeddingProvider (Ollama /api/embed or other providers)
- ChatLLMClient (Ollama /api/chat or other LLM backends)
- CrawlRunner (web crawlers)
- MarkdownStore (markdown and metadata persistence)
"""

from domain.ports.chat_llm import ChatLLMClient
from domain.ports.crawl import CrawlRunner
from domain.ports.embedding import EmbeddingProvider
from domain.ports.markdown_store import MarkdownStore
from domain.ports.rag_repository import RagRepository
from domain.ports.rerank_client import RerankClient

__all__ = [
    "ChatLLMClient",
    "CrawlRunner",
    "EmbeddingProvider",
    "MarkdownStore",
    "RagRepository",
    "RerankClient",
]
