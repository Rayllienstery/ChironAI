/**
 * Short model labels for live proxy notifications (RAG Fusion trace snapshot).
 */
export function traceModelFields(trace) {
  if (!trace) {
    return { headerShort: 'N/A', provider: null, requested: null, actual: null };
  }
  const req = trace.request || {};
  const providerTrace = trace.provider || trace.ollama || {};
  const provider = providerTrace.model != null && providerTrace.model !== '' ? String(providerTrace.model) : null;
  const requested =
    req.requested_model != null && req.requested_model !== '' ? String(req.requested_model) : null;
  const actual = req.actual_model != null && req.actual_model !== '' ? String(req.actual_model) : null;
  const headerShort = provider || actual || requested || 'N/A';
  return { headerShort, provider, requested, actual };
}
