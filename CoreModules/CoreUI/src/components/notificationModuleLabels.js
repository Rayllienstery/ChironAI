/** Display names for `source` keys passed by feature tabs. */

const LABELS = {
  crawler: 'Crawler / Indexer',
  'rag-tests': 'RAG Tests',
  rag: 'RAG / Qdrant',
  'rag-fusion-proxy': 'RAG Fusion Proxy',
  /** @deprecated persisted history may still use the old key */
  'dumb-proxy': 'RAG Fusion Proxy',
  'llm-proxy': 'LLM Proxy',
  'claw-proxy': 'Claw Code',
  logs: 'Logs',
  testing: 'Testing',
  dashboard: 'Dashboard',
  settings: 'Settings',
};

export function notificationModuleLabel(source) {
  if (!source || typeof source !== 'string') return 'CoreUI';
  return LABELS[source] || source.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
