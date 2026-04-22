# Setup Instructions

## Overview
ChironAI is split into:
- Backend (RAG proxy): retrieval + prompt building + chat calls.
- Frontend (WebUI): UI for chat/testing and RAG settings.
- Data: Qdrant collections created by the indexer.

## Steps
1. Configure environment variables (Ollama URLs, model names, etc.).
2. Configure config/rag.yaml.
3. Start Qdrant.
4. Run the indexer to populate Qdrant.
5. Start the RAG proxy/server.
6. Start the WebUI.

After indexing, the WebUI should show available collections and allow starting/stopping RAG.
