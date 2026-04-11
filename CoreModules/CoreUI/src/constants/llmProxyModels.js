/** Logical or legacy ids that are not literal Ollama image tags (for dropdown filtering). */
export const NON_OLLAMA_MODEL_IDS = ['ChironAI-Autocomplete', 'ChironAI-Worker', 'rag-ollama'];

export function isLogicalRagModelId(id) {
  return NON_OLLAMA_MODEL_IDS.includes(id);
}
