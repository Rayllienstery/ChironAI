# RAG Chunking Plan

This document describes how ChironAI turns crawled documentation into retrieval-ready chunks.

## Goals
- Preserve semantic structure (headings, sections, code blocks).
- Avoid noisy UI/navigation text.
- Keep chunk sizes within embedding limits.

## Strategy
- Extract logical sections from HTML/markdown.
- Render code blocks as fenced code.
- Split large sections into multiple chunks while keeping stable metadata.
- Store chunk text plus metadata (source, path, versions when available).

## Validation
- Ensure empty/near-empty sections are skipped.
- Ensure code fences are not accidentally flattened.
- Confirm that reranking improves ordering for version-focused questions.
