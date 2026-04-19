"""Compatibility wrapper to standalone rag_service retrieval helpers."""

from rag_service.config import get_retrieval_bool, get_retrieval_dict, get_retrieval_int, get_retrieval_list
from rag_service.domain.services.retrieval import *  # noqa: F401,F403


def expand_query_variants(question: str) -> list[str]:
    """
    Compatibility shim for legacy tests that patch retrieval config getters on this module.
    Standalone rag_service remains the canonical implementation.
    """
    q = (question or "").strip()
    if not q:
        return []
    if not get_retrieval_bool("query_expansion_enabled", False):
        return [q]
    max_v = max(1, get_retrieval_int("query_expansion_max_variants", 3))
    abbrev = get_retrieval_dict("query_expansion_abbreviations", {})
    variants: list[str] = [q]
    qlower = q.lower()
    for trigger, expansion in abbrev.items():
        trig = str(trigger).strip()
        if not trig or trig.lower() not in qlower:
            continue
        extra = f"{q} {expansion}".strip()
        if extra not in variants:
            variants.append(extra)
        if len(variants) >= max_v:
            break
    return variants[:max_v]
