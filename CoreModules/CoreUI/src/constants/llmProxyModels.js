/** Logical or legacy ids that are not literal Ollama image tags (for dropdown filtering). */
const NON_OLLAMA_MODEL_IDS = ['ChironAI-Autocomplete'];

export function isLogicalRagModelId(id) {
  return NON_OLLAMA_MODEL_IDS.includes(id);
}
