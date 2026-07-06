# RAG Collections

Retrieval-Augmented Generation (RAG) augments the LLM prompt with chunks from your documentation. In ChironAI, chunks live in **Qdrant collections**; the proxy decides **when** to retrieve, **which** collection to query, and **how** to rank results.

## Architecture (30-second version)

```
User question → RAG trigger? → Embed query → Qdrant search → (optional rerank)
     → Merge chunks into prompt → LLM provider → Answer + trace metadata
```

The WebUI surfaces each stage in **Model Tester** traces and **Logs**.

## Collections in Qdrant

A **collection** is a named vector index. Each point stores:

- Embedding vector(s) for semantic search
- Payload metadata (source path, title, symbol, framework, section, …)
- Text chunk used in the final prompt

Manage collections from **RAG / Qdrant**:

- List collections and point counts
- Open Qdrant dashboard (when exposed)
- Run ad-hoc retrieval tests against a collection
- Inspect keyword-collection helpers (when configured)

Collections appear in **LLM Proxy Builds** wizard only when the WebUI can reach Qdrant and list names successfully.

## Where the collection name comes from

The canonical precedence (highest wins) for `rag_collection`:

| Priority | Source | Example |
|----------|--------|---------|
| 1 | Request field `collection_name` | Client override per call |
| 2 | App setting `rag_collection` | Global WebUI setting |
| 3 | **LLM Proxy build** `rag_collection` | Per-build dropdown |
| 4 | Legacy `proxy_settings.rag_collection` | Older persisted blob |
| 5 | Default wiring / caller fallback | Host config |

Observability: proxy traces include `collection_name` plus `collection_source` so you can see which layer won.

## Global RAG Fusion settings

**RAG Fusion Proxy → Model settings** controls defaults when builds do not override:

- Default chat / embed / rerank models
- **RAG trigger threshold** — minimum score before retrieval runs (small talk may skip RAG)
- **Hybrid sparse** — blend dense retrieval with sparse/keyword signals
- **Rerank for RAG** — enable second-stage reranking
- **Web interaction** flags — optional web-augmented knowledge (DDG, fetch page, Wikipedia) when configured

Changes here affect all builds that inherit global collection/settings unless a build overrides them.

## Query processing (what happens to your question)

Before Qdrant sees the query, the retrieval layer may:

- Strip fenced code blocks from the question text
- Remove filler/stop phrases
- Expand API symbols (PascalCase types) and framework hints (UIKit vs SwiftUI)
- Apply **concept aliases** from host config to bias toward domain vocabulary

Intent inference (`symbol`, `framework`, `section_hint`) can add Qdrant filters so chunks matching the requested API surface rank higher.

Tune behaviour without code via `config/` retrieval dictionaries and `docs/RAG_BEHAVIOR.md` in the repository.

## Hybrid retrieval and rerank

When enabled:

1. **Dense** — embedding similarity against chunk vectors
2. **Sparse / hybrid** — keyword or BM25-style signal (collection-dependent)
3. **Rerank** — cross-encoder or rerank model re-orders top candidates

Use **RAG Tests** (Testing tab) for regression-style retrieval checks. Use **Model Tester** for end-to-end proxy + LLM behaviour.

## Empty collection dropdown

If **LLM Proxy Builds** shows no collections:

1. **RAG / Qdrant** — is Qdrant running? Any collections listed?
2. **Docker** — start Qdrant container if your deployment uses it
3. **Dependencies** — network/path issues to `localhost:6333` (default)
4. **Ingestion** — run **Crawler / Indexer** or your pipeline; empty Qdrant has nothing to list
5. Refresh the builds tab after Qdrant reports collections

A running Qdrant with zero collections still produces an empty dropdown — you must index first.

## Choosing collection strategy

| Scenario | Recommendation |
|----------|------------------|
| Single product docs | One collection + global default |
| Multiple codebases | One collection per repo/domain + per-build mapping |
| Experiments | Separate `*-staging` collection; swap on one build |
| Large corpus | Split by topic; use build ids as routing keys |

Keep collection names short, stable, and documented in your team wiki.

## Verification workflow

1. **RAG tab** — retrieval test with a phrase you know exists in docs
2. **Model Tester** — same question through a build with RAG enabled
3. Inspect trace:
   - `collection_name` / `collection_source`
   - `rag_steps` or equivalent retrieval timeline
   - Context preview (truncated in UI; full in journal metadata)
4. **Logs → RAG Fusion Journal** — open entry, read `metadata.trace` and `metadata.rag_context`

If retrieval test hits but Model Tester does not, suspect trigger threshold or build inheriting wrong collection.

## Performance tips

- Smaller, focused collections retrieve faster and with less noise than one giant index
- Re-embed when you change embedding models — old vectors are incompatible
- Raise trigger threshold if RAG runs on every casual message
- Disable rerank during early tuning to isolate embedding/chunk quality

## Related topics

- **Indexing Content** — how chunks get into Qdrant
- **LLM Proxy Builds** — per-build collection override
- **Troubleshooting** — RAG-specific failure modes
- **Logs & Debugging** — reading trace payloads
