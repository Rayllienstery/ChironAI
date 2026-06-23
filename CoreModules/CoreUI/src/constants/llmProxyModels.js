/** Logical or legacy ids that are not literal provider model ids (for dropdown filtering). */
const NON_PROVIDER_MODEL_IDS = ['ChironAI-Autocomplete'];

export function isLogicalRagModelId(id) {
  return NON_PROVIDER_MODEL_IDS.includes(id);
}
