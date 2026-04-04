/** Logical RAG chat ids from GET /api/webui/models (includes legacy alias). */
export const LOGICAL_RAG_MODEL_IDS = ['ChironAI-Worker', 'rag-ollama'];

export function isLogicalRagModelId(id) {
  return LOGICAL_RAG_MODEL_IDS.includes(id);
}
