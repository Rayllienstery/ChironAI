/**
 * Short model labels for live proxy notifications (RAG Fusion trace snapshot).
 */
export function traceModelFields(trace) {
  if (!trace) {
    return { headerShort: 'N/A', ollama: null, requested: null, actual: null };
  }
  const req = trace.request || {};
  const oll = trace.ollama || {};
  const ollama = oll.model != null && oll.model !== '' ? String(oll.model) : null;
  const requested =
    req.requested_model != null && req.requested_model !== '' ? String(req.requested_model) : null;
  const actual = req.actual_model != null && req.actual_model !== '' ? String(req.actual_model) : null;
  const headerShort = ollama || actual || requested || 'N/A';
  return { headerShort, ollama, requested, actual };
}
