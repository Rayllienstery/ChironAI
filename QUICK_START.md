# Quick Start

## 1) Prerequisites
- Python environment with project dependencies installed.
- Ollama running locally.
- Qdrant running and reachable.

## 2) Configure
Edit config/rag.yaml:
- 
ag.prompt: prompt name (e.g. system_rag_v1).
- context_chunk_chars, context_total_chars, 	op_k, confidence_threshold.

## 3) Start services
- Start the RAG proxy/server.
- Start the WebUI (if you use the frontend).

## 4) Use
- Crawl/index documentation sources.
- Ask questions in the WebUI or via the CLI.

For common issues, see TROUBLESHOOTING.md.
