"""
External docs RAG use cases.

Fetch → parse → chunk → embed → upsert; multi-collection RAG with merged context.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import urljoin

from external_docs_rag.domain.entities import (
    ExternalSource,
    IngestResult,
    RagContext,
    RagSourceConfig,
)
from external_docs_rag.domain.ports import ChunkSink, EmbeddingPort, FetchClient, RagSearchPort
from external_docs_rag.domain.services.chunking import chunk_quality_ok, split_markdown_into_chunks
from external_docs_rag.domain.services.context_ordering import (
    reorder_chunks_for_version_question,
    wants_version_or_requirements,
)
from external_docs_rag.domain.services.framework_candidates import (
    extract_candidate_framework_names,
    extract_framework_version_pairs,
)
from external_docs_rag.infrastructure.content_parser import parse_document_to_markdown
from external_docs_rag.infrastructure.github_discovery import (
    discover_and_fetch_readme,
    get_latest_release_tag,
    parse_raw_github_full_name,
    replace_ref_in_raw_github_url,
)
from external_docs_rag.infrastructure.github_tree import list_markdown_raw_urls


def fetch_on_demand_context(
    source: ExternalSource,
    fetch_client: FetchClient,
    context_max_chars: int,
    question: str | None = None,
    ref_override: str | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """
    Fetch docs from the web (e.g. GitHub raw), parse, chunk, and build a single context string.
    No embedding, no RAG write — for immediate use in the request.
    When question asks for version/requirements, chunks for those sections are prioritized.
    ref_override: when set, use this tag/branch in GitHub raw URL (e.g. "5.11.1" for a specific version).
    Returns (context_text, chunks_info for logging).
    """
    parts: list[str] = []
    chunks_info: list[dict[str, Any]] = []
    total = 0
    base = (
        replace_ref_in_raw_github_url(source.base_url, ref_override)
        if ref_override
        else source.base_url.rstrip("/")
    )
    for rel_path in source.paths:
        if total >= context_max_chars:
            break
        url = urljoin(base + "/", rel_path)
        doc = fetch_client.fetch(url)
        if doc is None:
            continue
        doc = doc.__class__(
            url=doc.url,
            content=doc.content,
            source_id=source.id,
            filename=doc.filename,
            content_type=doc.content_type,
        )
        md = parse_document_to_markdown(doc)
        if not md or len(md.strip()) < 50:
            continue
        raw_chunks = split_markdown_into_chunks(md)
        if question and wants_version_or_requirements(question):
            raw_chunks = reorder_chunks_for_version_question(raw_chunks)
        for chunk_text, section_path in raw_chunks:
            if total >= context_max_chars:
                break
            if not chunk_quality_ok(chunk_text):
                continue
            remaining = context_max_chars - total
            take = chunk_text[:remaining].rstrip() if len(chunk_text) > remaining else chunk_text
            if not take:
                continue
            parts.append(take)
            total += len(take) + 2
            take_len = len(take)
            take_preview_limit = 100
            take_preview = take[:take_preview_limit] + (
                "..." if take_len > take_preview_limit else ""
            )
            chunks_info.append({
                "source": source.id,
                "url": url,
                "path": rel_path,
                "label": source.collection_name,
                "text_length": take_len,
                "text_preview": take_preview,
            })
    context_text = "\n\n".join(parts)
    return context_text, chunks_info


def ingest_source_to_collection(
    source: ExternalSource,
    fetch_client: FetchClient,
    chunk_sink: ChunkSink,
    embed_provider: EmbeddingPort,
) -> IngestResult:
    """
    Ingest an external source: fetch URLs → parse → chunk → embed → write to collection.
    """
    errors: list[str] = []
    documents_fetched = 0
    all_chunks: list[dict[str, Any]] = []
    base = source.base_url.rstrip("/")
    for rel_path in source.paths:
        url = urljoin(base + "/", rel_path)
        doc = fetch_client.fetch(url)
        if doc is None:
            errors.append(f"fetch failed: {url}")
            continue
        doc = doc.__class__(
            url=doc.url,
            content=doc.content,
            source_id=source.id,
            filename=doc.filename,
            content_type=doc.content_type,
        )
        md = parse_document_to_markdown(doc)
        if not md or len(md.strip()) < 100:
            continue
        documents_fetched += 1
        raw_chunks = split_markdown_into_chunks(md)
        for chunk_text, section_path in raw_chunks:
            if not chunk_quality_ok(chunk_text):
                continue
            all_chunks.append({
                "text": chunk_text,
                "source_id": source.id,
                "path": rel_path,
                "url": url,
                "section_path": section_path,
            })
    if not all_chunks:
        return IngestResult(
            source_id=source.id,
            collection_name=source.collection_name,
            documents_fetched=documents_fetched,
            chunks_indexed=0,
            errors=errors,
        )
    texts = [c["text"] for c in all_chunks]
    try:
        vectors = embed_provider.embed_batch(texts)
    except Exception as e:
        errors.append(f"embed_batch: {e}")
        return IngestResult(
            source_id=source.id,
            collection_name=source.collection_name,
            documents_fetched=documents_fetched,
            chunks_indexed=0,
            errors=errors,
        )
    if len(vectors) != len(all_chunks):
        errors.append(f"embed count {len(vectors)} != chunks {len(all_chunks)}")
        return IngestResult(
            source_id=source.id,
            collection_name=source.collection_name,
            documents_fetched=documents_fetched,
            chunks_indexed=0,
            errors=errors,
        )
    vector_size = len(vectors[0])
    try:
        written = chunk_sink.write_chunks(
            source.collection_name,
            all_chunks,
            vectors,
            vector_size,
        )
    except Exception as e:
        errors.append(f"write_chunks: {e}")
        return IngestResult(
            source_id=source.id,
            collection_name=source.collection_name,
            documents_fetched=documents_fetched,
            chunks_indexed=0,
            errors=errors,
        )
    return IngestResult(
        source_id=source.id,
        collection_name=source.collection_name,
        documents_fetched=documents_fetched,
        chunks_indexed=written,
        errors=errors,
    )


def ingest_url_list_to_collection(
    urls: list[str],
    collection_name: str,
    framework_id: str,
    version: str | None,
    fetch_client: FetchClient,
    chunk_sink: ChunkSink,
    embed_provider: EmbeddingPort,
    on_indexed: Callable[[str, str, str | None, str], None] | None = None,
) -> IngestResult:
    """
    Fetch each URL, parse to markdown, chunk, embed, and write to the given collection.
    After successful write, calls on_indexed(collection_name, framework_id, version, last_refreshed_at)
    so the caller can update the collection registry (e.g. set_collection_meta).
    """
    errors: list[str] = []
    documents_fetched = 0
    all_chunks: list[dict[str, Any]] = []
    for url in urls:
        doc = fetch_client.fetch(url)
        if doc is None:
            errors.append(f"fetch failed: {url}")
            continue
        md = parse_document_to_markdown(doc)
        if not md or len(md.strip()) < 50:
            continue
        documents_fetched += 1
        # Derive path from URL (last path segment)
        path = (url.rstrip("/").split("/")[-1]) if url else ""
        raw_chunks = split_markdown_into_chunks(md)
        for chunk_text, section_path in raw_chunks:
            if not chunk_quality_ok(chunk_text):
                continue
            all_chunks.append({
                "text": chunk_text,
                "source_id": framework_id,
                "path": path,
                "url": url,
                "section_path": section_path,
            })
    if not all_chunks:
        return IngestResult(
            source_id=framework_id,
            collection_name=collection_name,
            documents_fetched=documents_fetched,
            chunks_indexed=0,
            errors=errors,
        )
    texts = [c["text"] for c in all_chunks]
    try:
        vectors = embed_provider.embed_batch(texts)
    except Exception as e:
        errors.append(f"embed_batch: {e}")
        return IngestResult(
            source_id=framework_id,
            collection_name=collection_name,
            documents_fetched=documents_fetched,
            chunks_indexed=0,
            errors=errors,
        )
    if len(vectors) != len(all_chunks):
        errors.append(f"embed count {len(vectors)} != chunks {len(all_chunks)}")
        return IngestResult(
            source_id=framework_id,
            collection_name=collection_name,
            documents_fetched=documents_fetched,
            chunks_indexed=0,
            errors=errors,
        )
    vector_size = len(vectors[0])
    try:
        written = chunk_sink.write_chunks(collection_name, all_chunks, vectors, vector_size)
    except Exception as e:
        errors.append(f"write_chunks: {e}")
        return IngestResult(
            source_id=framework_id,
            collection_name=collection_name,
            documents_fetched=documents_fetched,
            chunks_indexed=0,
            errors=errors,
        )
    if on_indexed and written > 0:
        try:
            last_refreshed_at = datetime.now(timezone.utc).isoformat()
            on_indexed(collection_name, framework_id, version, last_refreshed_at)
        except Exception:  # safe: on_indexed callback must not fail ingest
            pass
    return IngestResult(
        source_id=framework_id,
        collection_name=collection_name,
        documents_fetched=documents_fetched,
        chunks_indexed=written,
        errors=errors,
    )


def ingest_github_repo_markdown(
    owner: str,
    repo: str,
    ref: str,
    collection_name: str,
    framework_id: str,
    fetch_client: FetchClient,
    chunk_sink: ChunkSink,
    embed_provider: EmbeddingPort,
    max_depth: int = 3,
    on_indexed: Callable[[str, str, str | None, str], None] | None = None,
) -> IngestResult:
    """
    List .md files in the repo at ref (path depth <= max_depth), fetch, chunk, embed, write to collection.
    Calls on_indexed(collection_name, framework_id, version, last_refreshed_at) after success.
    """
    urls = list_markdown_raw_urls(owner, repo, ref, max_depth=max_depth)
    if not urls:
        return IngestResult(
            source_id=framework_id,
            collection_name=collection_name,
            documents_fetched=0,
            chunks_indexed=0,
            errors=["No .md files found or GitHub API failed"],
        )
    return ingest_url_list_to_collection(
        urls=urls,
        collection_name=collection_name,
        framework_id=framework_id,
        version=ref,
        fetch_client=fetch_client,
        chunk_sink=chunk_sink,
        embed_provider=embed_provider,
        on_indexed=on_indexed,
    )


def resolve_rag_sources_for_request(
    question: str,
    _messages: list[dict[str, Any]],
    body_rag_sources: list[str] | None,
    config: list[RagSourceConfig],
) -> list[RagSourceConfig]:
    """
    Resolve which RAG sources (collections + top_k) to use for this request.
    If body_rag_sources is set, use those collection names (matched to config).
    Else: include every source whose trigger_keywords appear in question, and always
    include sources with empty trigger_keywords (main/default collection).
    """
    result: list[RagSourceConfig] = []
    question_lower = (question or "").lower()
    if body_rag_sources:
        for name in body_rag_sources:
            for c in config:
                if c.collection_name == name:
                    result.append(c)
                    break
        return result
    for c in config:
        if not c.trigger_keywords or any(kw.lower() in question_lower for kw in c.trigger_keywords):
            result.append(c)
    return result


def _truncate_at_boundary(chunk: str, max_chars: int) -> str:
    """Truncate at sentence or line boundary to avoid cutting mid-sentence."""
    if len(chunk) <= max_chars:
        return chunk
    cut = chunk.rfind(". ", 0, max_chars + 1)
    if cut <= max_chars // 2:
        cut = chunk.rfind("\n", 0, max_chars + 1)
    if cut <= max_chars // 2:
        cut = chunk.rfind(" ", 0, max_chars + 1)
    if cut > 0:
        return chunk[: cut + 1].rstrip()
    return chunk[:max_chars].rstrip()


def build_merged_rag_context(
    question: str,
    rag_sources: list[RagSourceConfig],
    rag_search: RagSearchPort,
    embed_provider: EmbeddingPort,
    context_chunk_chars: int,
    context_total_chars: int,
    fetch_client: FetchClient | None = None,
    external_sources: list[ExternalSource] | None = None,
    fresh_collection_names: set[str] | None = None,
) -> tuple[RagContext, dict[str, float]]:
    """
    Build RAG context: for sources with on_demand_fetch, fetch from web and parse;
    for any other framework name in the question, discover via GitHub and fetch README;
    for the rest, search RAG. Merge into one context block.
    When fresh_collection_names is set, only search RAG for collections in that set
    (so stale/missing frameworks still get on-demand fetch but no vector search).
    """
    import time
    timings: dict[str, float] = {
        "embed_s": 0.0,
        "search_s": 0.0,
        "fetch_s": 0.0,
        "discovery_s": 0.0,
        "total_rag_s": 0.0,
        # Token estimates for UI trace (approximate, len/4 heuristic).
        "embed_tokens_in": 0.0,
        "rerank_prompt_tokens_in": 0.0,
        "fetch_tokens_in": 0.0,
        "discovery_tokens_in": 0.0,
    }
    if not question or not question.strip():
        return RagContext("", [], 0.0), timings
    rag_sources = rag_sources or []
    external_by_id = {s.id: s for s in (external_sources or [])}
    parts: list[str] = []
    chunks_info: list[dict[str, Any]] = []
    total_used = 0
    max_score = 0.0
    already_covered: set[str] = set()

    version_pairs = extract_framework_version_pairs(question)
    ref_by_source_id: dict[str, str] = {}
    for name, version in version_pairs:
        if not version:
            continue
        name_lower = name.lower()
        for cfg in rag_sources:
            if not cfg.on_demand_fetch or not cfg.external_source_id:
                continue
            if name_lower == (cfg.external_source_id or "").lower():
                ref_by_source_id[cfg.external_source_id] = version
                break
            if any(name_lower == (kw or "").lower() for kw in (cfg.trigger_keywords or [])):
                ref_by_source_id[cfg.external_source_id] = version
                break

    # On-demand: fetch from internet for sources with on_demand_fetch
    if fetch_client and external_sources:
        t0 = time.perf_counter()
        on_demand_chars = context_total_chars // 2
        for cfg in rag_sources:
            if not cfg.on_demand_fetch or not cfg.external_source_id:
                continue
            source = external_by_id.get(cfg.external_source_id)
            if not source:
                continue
            ref_override = ref_by_source_id.get(cfg.external_source_id)
            resolved_latest: str | None = None
            if ref_override is None and wants_version_or_requirements(question):
                full_name = parse_raw_github_full_name(source.base_url)
                if full_name:
                    resolved_latest = get_latest_release_tag(full_name)
                    ref_override = resolved_latest
            ctx_text, infos = fetch_on_demand_context(
                source,
                fetch_client,
                on_demand_chars,
                question=question,
                ref_override=ref_override,
            )
            if ctx_text:
                if resolved_latest:
                    ctx_text = f"Latest release version: {resolved_latest}\n\n{ctx_text}"
                if cfg.label:
                    parts.append(f"--- {cfg.label} (fetched from web) ---")
                    total_used += len(cfg.label) + 30
                parts.append(ctx_text)
                total_used += len(ctx_text) + 2
                timings["fetch_tokens_in"] += 0 if not ctx_text else max(1, int(len(ctx_text) / 4))
                for kw in cfg.trigger_keywords:
                    already_covered.add(kw.lower())
                already_covered.add(cfg.external_source_id.lower())
                for info in infos:
                    chunks_info.append({
                        "index": len(chunks_info) + 1,
                        "score": "N/A",
                        "url": info.get("url", "N/A"),
                        "source": info.get("source", "N/A"),
                        "label": cfg.label or cfg.collection_name,
                            "text_length": info.get("text_length"),
                            "text_preview": info.get("text_preview"),
                    })
        timings["fetch_s"] = time.perf_counter() - t0

    # Generic discovery: extract framework-like names from question, discover on GitHub if not already covered
    version_by_name = {name: v for name, v in version_pairs if v}
    if fetch_client and total_used < context_total_chars:
        t0 = time.perf_counter()
        candidates = extract_candidate_framework_names(question)
        remaining = context_total_chars - total_used
        discovery_chars_per = max(1500, remaining // 3)
        for name in candidates:
            if name.lower() in already_covered:
                continue
            result = discover_and_fetch_readme(
                name,
                fetch_client,
                discovery_chars_per,
                question=question,
                version_ref=version_by_name.get(name),
            )
            if result is None:
                continue
            ctx_text, infos = result
            if not ctx_text:
                continue
            parts.append(f"--- {name} (discovered from GitHub) ---")
            total_used += len(name) + 30
            parts.append(ctx_text)
            total_used += len(ctx_text) + 2
            timings["discovery_tokens_in"] += 0 if not ctx_text else max(1, int(len(ctx_text) / 4))
            already_covered.add(name.lower())
            for info in infos:
                chunks_info.append({
                    "index": len(chunks_info) + 1,
                    "score": "N/A",
                    "url": info.get("url", "N/A"),
                    "source": info.get("source", "N/A"),
                    "label": info.get("label", name),
                    "text_length": info.get("text_length"),
                    "text_preview": info.get("text_preview"),
                })
            if total_used >= context_total_chars:
                break
        timings["discovery_s"] = time.perf_counter() - t0

    # RAG search for sources that are not on-demand (or when on-demand returned nothing)
    rag_sources_to_search = [c for c in rag_sources if not (c.on_demand_fetch and c.external_source_id and external_by_id.get(c.external_source_id))]
    if fresh_collection_names is not None:
        rag_sources_to_search = [c for c in rag_sources_to_search if c.collection_name in fresh_collection_names]
    all_hits: list[tuple[str, dict]] = []
    if rag_sources_to_search:
        t0 = time.perf_counter()
        try:
            vec = embed_provider.embed(question)
        except Exception:
            vec = []
        timings["embed_s"] = time.perf_counter() - t0
        timings["embed_tokens_in"] += 0 if not question else max(1, int(len(question) / 4))
        if vec:
            t0 = time.perf_counter()
            for cfg in rag_sources_to_search:
                hits = rag_search.search(cfg.collection_name, vec, cfg.top_k)
                for h in hits:
                    all_hits.append((cfg.label or cfg.collection_name, h))
            timings["search_s"] = time.perf_counter() - t0
        if all_hits:
            max_score = max(h.get("score", 0.0) for _, h in all_hits)
            remaining_chars = context_total_chars - total_used
            current_label: str | None = None
            for idx, (label, h) in enumerate(all_hits, start=1):
                if total_used >= context_total_chars or remaining_chars <= 0:
                    break
                payload = h.get("payload") or {}
                txt = (payload.get("text") or "").strip()
                if not txt:
                    continue
                snippet = _truncate_at_boundary(txt, min(context_chunk_chars, remaining_chars))
                if not snippet:
                    continue
                if label != current_label:
                    if label:
                        parts.append(f"--- {label} ---")
                        total_used += len(label) + 12
                        remaining_chars -= len(label) + 12
                    current_label = label
                parts.append(snippet)
                total_used += len(snippet) + 2
                remaining_chars -= len(snippet) + 2
                score = h.get("score", 0.0)
                chunks_info.append({
                    "index": len(chunks_info) + 1,
                    "score": f"{score:.4f}" if score else "N/A",
                    "url": payload.get("url") or "N/A",
                    "source": payload.get("source") or "N/A",
                    "label": label,
                    "text_length": len(snippet),
                    "text_preview": snippet[:100] + ("..." if len(snippet) > 100 else ""),
                })
    timings["total_rag_s"] = timings["embed_s"] + timings["search_s"] + timings["fetch_s"] + timings["discovery_s"]
    context_text = "\n\n".join(parts)
    return RagContext(context_text=context_text, chunks_info=chunks_info, max_score=max_score), timings


__all__ = [
    "build_merged_rag_context",
    "fetch_on_demand_context",
    "ingest_github_repo_markdown",
    "ingest_source_to_collection",
    "ingest_url_list_to_collection",
    "resolve_rag_sources_for_request",
]
