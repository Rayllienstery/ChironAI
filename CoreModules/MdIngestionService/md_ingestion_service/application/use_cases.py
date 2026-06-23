"""
MD Ingestion use cases.

Orchestrate: source_store -> filter -> normalize -> chunk -> output_sink.
"""

from __future__ import annotations

from typing import Any

from md_ingestion_service.domain.entities import FilterRule
from md_ingestion_service.domain.ports import OutputSink, SourceStore
from md_ingestion_service.domain.services.chunking_policy import chunks_for_document
from md_ingestion_service.domain.services.filtering import apply_filter, default_filter_rule
from md_ingestion_service.domain.services.indexing_prepare import prepare_markdown_for_indexing


def ingest_local_markdown(
    source_id: str,
    base_path: str,
    source_store: SourceStore,
    output_sink: OutputSink,
    collection: str,
    filter_rule: FilterRule | None = None,
) -> dict[str, Any]:
    """
    Ingest markdown from a local path: list files -> filter -> prepare (indexing rules + md_indexer) -> chunk -> write to sink.
    Returns summary: files_processed, chunks_indexed, errors.
    """
    rule = filter_rule or default_filter_rule()
    errors: list[str] = []
    files_processed = 0
    chunks_indexed = 0
    try:
        relative_paths = source_store.list_files(source_id, base_path)
    except Exception as e:
        return {"files_processed": 0, "chunks_indexed": 0, "errors": [str(e)]}
    all_chunks: list[dict[str, Any]] = []
    for rel in relative_paths:
        try:
            md = source_store.read_file(source_id, base_path, rel)
            if md is None:
                continue
            if not apply_filter(md, rule):
                continue
            prep = prepare_markdown_for_indexing(md.filename, md.content)
            if prep.skipped:
                continue
            path = md.path or md.filename
            url = (prep.page_meta or {}).get("url") or ""
            chunks = chunks_for_document(
                prep.body_md,
                source_id=source_id,
                filename=md.filename,
                path=path,
                url=url,
            )
            if not chunks:
                continue
            files_processed += 1
            all_chunks.extend(chunks)
        except Exception as e:
            errors.append(f"{rel}: {e}")
    if all_chunks:
        try:
            n = output_sink.write_chunks(collection, all_chunks, vectors=None)
            chunks_indexed = n
        except Exception as e:
            errors.append(f"output_sink: {e}")
    return {
        "files_processed": files_processed,
        "chunks_indexed": chunks_indexed,
        "errors": errors,
    }


def dry_run_ingest(
    source_id: str,
    base_path: str,
    source_store: SourceStore,
    filter_rule: FilterRule | None = None,
) -> dict[str, Any]:
    """Same as ingest but do not write to sink; return counts and sample chunks."""
    rule = filter_rule or default_filter_rule()
    relative_paths = source_store.list_files(source_id, base_path)
    files_processed = 0
    total_chunks = 0
    sample_chunks: list[dict[str, Any]] = []
    for rel in relative_paths[:20]:
        md = source_store.read_file(source_id, base_path, rel)
        if md is None or not apply_filter(md, rule):
            continue
        prep = prepare_markdown_for_indexing(md.filename, md.content)
        if prep.skipped:
            continue
        url = (prep.page_meta or {}).get("url")
        chunks = chunks_for_document(
            prep.body_md,
            source_id=source_id,
            filename=md.filename,
            path=md.path or md.filename,
            url=url,
        )
        if chunks:
            files_processed += 1
            total_chunks += len(chunks)
            if len(sample_chunks) < 3:
                sample_chunks.extend(chunks[:1])
    return {
        "files_processed": files_processed,
        "total_chunks": total_chunks,
        "paths_scanned": len(relative_paths),
        "sample_chunks": sample_chunks[:3],
    }


__all__ = ["ingest_local_markdown", "dry_run_ingest"]
