# Qdrant vector modes

`rag_service.infrastructure.qdrant_repository.QdrantRagRepository` supports only:

| Mode | Collection schema | Search API |
|------|-------------------|------------|
| `named_dense` | `vectors.dense` named config | `POST .../points/search` with `vector.name = dense` |
| `hybrid` | `vectors.dense` + `sparse_vectors.sparse` | `POST .../points/query` (RRF); degrades to dense search on query errors |

Unnamed single-vector collections (plain `vectors: 128`) are **not supported**. Recreate
collections via WebUI crawler, external-docs sink, or `dense_vectors_config()` helpers in
`infrastructure.rag.qdrant_point_builder`.

`external_docs_rag.infrastructure.QdrantRagSearchAdapter` delegates search to
`QdrantRagRepository` (named dense path only; no duplicate HTTP client).

## Upsert shape

Use `build_named_vectors(text, embedding, hybrid_sparse=...)` so points always carry
`{"dense": [...]}` or dense+sparse named payloads.

## Tests

[`tests/rag_service/test_qdrant_vector_modes.py`](../../../tests/rag_service/test_qdrant_vector_modes.py)
