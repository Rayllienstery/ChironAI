/** Display names for `source` keys passed by feature tabs. */

const LABELS = {
  crawler: 'Crawler / Indexer',
  'rag-tests': 'RAG Tests',
  rag: 'RAG / Qdrant',
  'llm-proxy': 'LLM Proxy',
  'claw-proxy': 'Claw Proxy',
  logs: 'Logs',
  testing: 'Testing',
  dashboard: 'Dashboard',
  settings: 'Settings',
};

export function notificationModuleLabel(source) {
  if (!source || typeof source !== 'string') return 'CoreUI';
  return LABELS[source] || source.replace(/-/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}
