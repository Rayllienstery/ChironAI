import { RAG_TESTS_LAST_USED_KEY } from './constants';

function modelTagLooksCloud(modelId) {
  const s = String(modelId || '').trim().toLowerCase();
  if (!s) return false;
  return s.includes(':cloud') || s.endsWith('-cloud');
}

export function confirmCloudRagRun(modelId) {
  if (!modelTagLooksCloud(modelId)) return true;
  return window.confirm(
    'Cloud-tagged model selected: running RAG Tests may consume paid tokens. Continue?'
  );
}

export function ragRetrieved(row) {
  if (!row) return false;
  if (row.retrieval_used != null) return Boolean(row.retrieval_used);
  return Boolean(row.rag_used);
}

export function groundingOverlap(row) {
  return row?.grounding_overlap === true;
}

export function strictRagOk(row) {
  return row?.strict_rag_ok === true;
}

export function yesNo(value) {
  if (value == null) return '-';
  return value ? 'Yes' : 'No';
}

export function metricVersionLabel(runOrRow) {
  return String(runOrRow?.metrics_version || 'legacy_unknown');
}

export function loadLastUsedRagTestsSettings() {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(RAG_TESTS_LAST_USED_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

export function sortModelsCloudFirst(list) {
  const items = Array.isArray(list) ? [...list] : [];
  const byName = (a, b) => {
    const an = String(a?.name || a?.id || '').toLowerCase();
    const bn = String(b?.name || b?.id || '').toLowerCase();
    return an.localeCompare(bn);
  };
  const cloud = [];
  const other = [];
  items.forEach((m) => {
    if (modelTagLooksCloud(m?.id || m?.name || '')) cloud.push(m);
    else other.push(m);
  });
  cloud.sort(byName);
  other.sort(byName);
  return [...cloud, ...other];
}

export function isTransientFetchLikeError(message) {
  const lower = String(message || '').toLowerCase();
  return (
    lower.includes('failed to fetch') ||
    lower.includes('networkerror') ||
    lower.includes('load failed') ||
    lower.includes('typeerror: failed to fetch')
  );
}
