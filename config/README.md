# Configuration Guide

## Overview

ChironAI uses YAML-based configuration files organized by domain. All configs support environment variable overrides for local experimentation without modifying files.

## Structure

```
config/
├── rag.yaml          # RAG context limits, model ID, reasoning levels
├── retrieval.yaml    # Vector search, reranking, query preprocessing
├── crawler.yaml      # Web crawling concurrency, timeouts, path filters
├── indexing.yaml     # Content filtering, chunking, embedding batch sizes
├── models.yaml       # Ollama endpoints, model names, generation options
└── server.yaml       # Flask server host/port, Qdrant connection, build proxy
```

## Usage

### In Python Code

```python
from config import (
    get_rag_int,
    get_retrieval_int,
    get_crawler_int,
    get_indexing_int,
    get_ollama_chat_model,
    get_qdrant_url,
    # ... etc
)

# Get integer config with default
top_k = get_rag_int("top_k", 4)

# Get model name (env override supported)
model = get_ollama_chat_model()
```

### Environment Overrides

Most configs can be overridden via environment variables:

```bash
# Override Ollama model
export OLLAMA_CHAT_MODEL="custom-model:tag"

# Override Qdrant URL
export QDRANT_URL="http://remote-host:6333"

# Override server port
export SERVER_PORT=9000

# RAG context limits (override rag.yaml; used by WebUI defaults and param loaders)
export RAG_CONTEXT_CHUNK_CHARS=1200
export RAG_CONTEXT_TOTAL_CHARS=8000

# Retrieval vector search breadth (override retrieval.yaml `top_k`; `get_retrieval_int("top_k", ...)`)
export RAG_TOP_K=12
```

## Configuration Files

### RAG limits: global defaults vs LLM Proxy Builds

| Knob | YAML | Env (read in code) | Per-request (dumb build id) |
|------|------|--------------------|-----------------------------|
| Chunk / total context chars | `rag.yaml` (`context_chunk_chars`, `context_total_chars`) | `RAG_CONTEXT_CHUNK_CHARS`, `RAG_CONTEXT_TOTAL_CHARS` (`get_rag_int`) | Optional build fields `context_chunk_chars`, `context_total_chars`; merged via `merge_build_into_proxy_settings` into `proxy_settings` and applied in LLM Proxy after build selection. |
| Retrieval `top_k` | `retrieval.yaml` (`top_k`, etc.) | `RAG_TOP_K` overrides `get_retrieval_int("top_k", …)` | Optional build field `rag_top_k` (same merge path). |

Passthrough requests (concrete Ollama tag, no build id) still use YAML/env and collection-specific params from `get_rag_answer_params`; they do not read build fields.

### rag.yaml
Controls RAG context size and model behavior:
- `context_chunk_chars`: Max chars per chunk (default: 1000)
- `context_total_chars`: Total context limit (default: 7000)
- `top_k`: Candidates per search (default: 4)
- `confidence_threshold`: Min score for "confirmed" RAG (default: 0.75)
- `model_id`: Deprecated; use `OLLAMA_CHAT_MODEL` / `ollama.chat_model` for default chat tag
- `reasoning_level_models`: Model name substrings supporting reasoning levels

### retrieval.yaml
Controls query processing and vector search:
- `max_embed_text_length`: Max chars sent to embedding model (default: 400)
- `top_k`: Default candidates per search (default: 8)
- `multi_chunk_top_k`: Top-K for multi-chunk queries (default: 16)
- `rerank_max_candidates`: Candidates sent to rerank LLM (default: 12)
- `final_context_k`: Chunks actually used in prompt (default: 4)
- `doc_type_preferred_for_qa`: Document types prioritized for Q&A
- `doc_type_weight`: Scoring weights by document type
- `multi_chunk_keywords`: Keywords triggering multi-chunk retrieval
- `retrieval_stop_words`: Words stripped from queries
- `coverage_aware_selection`: When true, final chunk list after rerank favors covering distinct target concepts (symbols + `concept_aliases` matches + optional `coverage_extra_terms`) instead of only the top‑K by relevance order
- `coverage_extra_terms`: List of phrases (matched as substrings in the question) added as coverage targets when `coverage_aware_selection` is enabled
- `concept_expansion_enabled`: When true, runs a second vector search after pass 1 using seeds from the question + top hit texts, expanded via `concept_expansion_map`, then merges new hits before rerank
- `concept_expansion_map`: Map of lowercase seed term → space-separated related terms (e.g. Swift concurrency)
- `concept_expansion_seed_hits`: Number of top pass-1 hits scanned for API symbols used as seeds
- `concept_expansion_max_terms`: Max expanded terms appended to the pass-2 embed query
- `concept_expansion_pass2_top_k`: Vector search `top_k` for the second pass
- `coverage_gate_enabled`: When true and heuristic target concepts exist, if `coverage_ratio` is below `coverage_gate_min_percent`, widen `final_k` once from the existing rerank pool (no re-embed)
- `coverage_gate_min_percent`: Integer 0–100; threshold for the gate (default 75)
- `coverage_gate_boost_final_k`: How many extra chunks to allow when the gate fires
- `coverage_gate_max_final_k`: Cap on final chunk count after widening
- `coverage_retry_supplemental_search_enabled`: Optional extra embed+search using missing concept strings, then rerank and finalize again (off by default)
- `coverage_retry_top_k`, `coverage_retry_max_missing_terms`, `coverage_retry_final_k`: Tune supplemental search; `coverage_retry_final_k` 0 means use `coverage_gate_max_final_k`
- `structured_rag_context_enabled`: Prepend Concepts/Evidence headings and numbered snippets in the RAG context block

### crawler.yaml
Controls web crawling behavior:
- `concurrency`: Parallel fetch limit (default: 6)
- `goto_timeout_ms`: Page load timeout (default: 30000)
- `dom_ready_wait_ms`: Wait after DOM ready for SPA (default: 2500)
- `max_retries_429`: Retry attempts for rate limits (default: 3)
- `backoff_base_sec`: Exponential backoff base (default: 2)
- `backoff_max_sec`: Max backoff delay (default: 60)
- `framework_root_prefixes`: URL path prefixes to crawl (whitelist)
- `excluded_path_substrings`: Path substrings to skip (blacklist)

### indexing.yaml
Controls content filtering and chunking:
- Minimum meaningful body: configure via MD pipeline step **`reject_low_signal_body`** in `config/md_pipelines/*.json` (`min_chars`, `min_words`, `min_alpha_ratio`), not this file.
- `chunk_max_size`: Max chars per chunk (default: 1200)
- `chunk_min_size`: Min chars per chunk (default: 300)
- `min_chunk_words`: Min word count per chunk (default: 25)
- `min_chunk_alpha_ratio`: Min alphabetic ratio (default: 0.2)
- `batch_upsert_size`: Qdrant upsert batch size (default: 200)
- `embed_batch_size`: Embedding batch size (default: 6)
- `embed_request_timeout`: Embedding timeout seconds (default: 300)
- `exclude_filename_substrings`: Filename patterns to skip
- `exclude_content_substrings`: Content markers for low-value pages
- `local_ingest`: Separate config for `ingest_markdown_local.py`

### models.yaml
Controls Ollama endpoints and models:
- `chat_url`: `/api/chat` endpoint URL
- `generate_url`: `/api/generate` endpoint URL
- `embed_url`: `/api/embed` endpoint URL
- `chat_model`: Model name for chat completion
- `embed_model`: Model name for embeddings
- `timeout_seconds`: Default HTTP timeout
- `chat_options`: Default generation options (num_predict, temperature, top_p)

### server.yaml
Controls server and Qdrant connection:
- `server.host`: Flask bind address (default: "0.0.0.0")
- `server.port`: Flask port (default: 8080)
- `qdrant.url`: Qdrant HTTP API URL (default: "http://localhost:6333")
- `qdrant.collection_name`: Collection name — must exist in Qdrant (env `QDRANT_COLLECTION_NAME` overrides)

## Best Practices

1. **Don't commit sensitive data**: Use environment variables for API keys, tokens, or production URLs.
2. **Version control configs**: Keep YAML files in Git for reproducibility.
3. **Document changes**: Update YAML comments when adding new parameters.
4. **Test defaults**: Ensure default values work out-of-the-box for new users.
5. **Use typed getters**: Always use `get_*_int()`, `get_*_float()`, etc. for type safety.

## Future Improvements

- [ ] Add config validation (type checking, range validation)
- [ ] Add config schema documentation (JSON Schema)
- [ ] Add example configs for different scenarios (dev, prod, testing)
- [ ] Add config hot-reload support (reload on file change)
- [ ] Add config diff tool (compare configs across environments)
