# Troubleshooting

## RAG returns irrelevant answers
- Check that the Qdrant collection is indexed and not empty.
- Increase 	op_k and/or adjust confidence_threshold.
- Verify the reranker model (if enabled).

## RAG never triggers
- Check greeting/skip heuristics and required keyword configuration.
- Confirm that your question contains enough technical signals.

## Errors from Ollama endpoints
- Ensure the configured Ollama base URL is reachable.
- Verify that the configured chat/embedding/rerank models exist in Ollama.

## WebUI connection issues
- Ensure backend host/port match the WebUI configuration.
- Verify CORS or proxy settings if applicable.
