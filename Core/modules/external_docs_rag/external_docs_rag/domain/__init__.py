"""Domain layer: entities and ports."""

from external_docs_rag.domain.entities import (
    ExternalSource,
    FetchedDocument,
    IngestResult,
    RagContext,
    RagSourceConfig,
)

__all__ = [
    "ExternalSource",
    "FetchedDocument",
    "IngestResult",
    "RagContext",
    "RagSourceConfig",
]
