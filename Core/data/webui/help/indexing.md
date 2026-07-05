# Indexing Content

The **Crawler** tab and related ingestion paths feed documents into Qdrant for RAG.

## Typical flow

1. Configure crawl sources or upload paths (per your deployment).
2. Run indexing jobs from **Crawler** or automated schedules.
3. Confirm the target **collection** appears under **RAG**.
4. Attach the collection to a build or global RAG settings.

## Chunking and metadata

Ingestion pipelines split documents into chunks with metadata (source URL, title, etc.). Retrieval tests show which chunks match a query—use them to tune chunk size and overlap in your indexer config.

## Re-indexing

After schema or embedding model changes, re-index affected collections. Old vectors may produce poor matches until the collection is rebuilt.

## Permissions

Ensure the WebUI process can reach file shares or HTTP sources configured for crawling. Network errors surface in **Logs** and the crawler job status panel.
