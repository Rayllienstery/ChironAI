# RAG Collections

RAG (Retrieval-Augmented Generation) attaches relevant document chunks to model prompts.

## Collections in Qdrant

Collections live in your Qdrant instance. The **RAG** tab lists available collections and lets you run retrieval tests against them.

## Precedence

When multiple sources define a collection, ChironAI applies this order (highest wins):

1. Per-request override (API field)
2. **Build-level** collection (LLM Proxy build)
3. Global proxy / model settings
4. System default (if configured)

See `docs/RAG_BEHAVIOR.md` in the repository for full details.

## Empty collection dropdown

If the build wizard shows no collections:

- Confirm Qdrant is running and reachable from the WebUI host.
- Create or ingest content via **Crawler** or your ingestion pipeline.
- Refresh the builds tab after Qdrant reports the collection.

## Testing retrieval

Use **RAG Tests** or **Model Tester** with RAG enabled to inspect `collection_name` and trace metadata in responses.
