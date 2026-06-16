import {
  CHIRONAI_RAG_TRACE_STORAGE_KEY,
} from '../RagTraceTimeline';

export function readMirroredRagTraceFromStorage() {
  try {
    const raw = sessionStorage.getItem(CHIRONAI_RAG_TRACE_STORAGE_KEY);
    if (!raw) return null;
    const o = JSON.parse(raw);
    if (Array.isArray(o.trace) && o.trace.length > 0) {
      return { steps: o.trace, latencyMs: o.latencyMs ?? null };
    }
  } catch (_) {
    /* ignore */
  }
  return null;
}

export function wordsInMultipleCollections(collections) {
  const wordToCollections = new Map();
  (collections || []).forEach((c) => {
    const id = c.id;
    (c.keywords || []).forEach((k) => {
      const low = (k || '').toLowerCase().trim();
      if (!low) return;
      if (!wordToCollections.has(low)) wordToCollections.set(low, new Set());
      wordToCollections.get(low).add(id);
    });
  });
  const out = [];
  wordToCollections.forEach((ids, word) => {
    if (ids.size > 1) out.push(word);
  });
  return out;
}

export function capitalize(word) {
  const s = (word || '').trim();
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}
