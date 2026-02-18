"""
Domain entities for TMRagFetcher.

Entities represent core business concepts such as RAG chunks, queries,
retrieval results, crawl sources, indexed pages, and embedding requests.
"""

from domain.entities import crawl, rag

__all__ = ["crawl", "rag"]
