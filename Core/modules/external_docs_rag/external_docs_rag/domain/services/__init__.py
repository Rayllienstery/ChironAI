"""Domain services: chunking, framework candidate extraction, and context ordering."""

from external_docs_rag.domain.services.chunking import (
    chunk_quality_ok,
    split_markdown_into_chunks,
)
from external_docs_rag.domain.services.context_ordering import (
    reorder_chunks_for_version_question,
    wants_version_or_requirements,
)
from external_docs_rag.domain.services.framework_candidates import (
    extract_candidate_framework_names,
    extract_framework_version_pairs,
)

__all__ = [
    "chunk_quality_ok",
    "extract_candidate_framework_names",
    "extract_framework_version_pairs",
    "reorder_chunks_for_version_question",
    "split_markdown_into_chunks",
    "wants_version_or_requirements",
]
