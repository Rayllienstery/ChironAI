import { API_BASE, extractApiError } from './http.js';
import { withRemoteRevealPinInit, setRemoteRevealPin } from './remoteRevealPin.js';

function throwProxyApiError(data, fallback, response) {
  const err = new Error(extractApiError(data, fallback));
  err.code = data?.code || null;
  err.status = response?.status;
  throw err;
}

export async function getLlmProxyStatus() {
  const response = await fetch(`${API_BASE}/llm-proxy/status`);
  if (!response.ok) {
    throw new Error('Failed to get LLM Proxy status');
  }
  return response.json();
}

export async function getLlmProxyApiKeyStatus() {
  const response = await fetch(`${API_BASE}/llm-proxy/api-key`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to get LLM Proxy API key status'));
  }
  return data;
}

export async function generateLlmProxyApiKey() {
  const response = await fetch(`${API_BASE}/llm-proxy/api-key/generate`, {
    method: 'POST',
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to generate LLM Proxy API key'));
  }
  return data;
}

export async function revealLlmProxyApiKey(pin = null) {
  const options = {
    method: 'POST',
  };
  if (pin) {
    setRemoteRevealPin(pin);
    options.headers = { 'Content-Type': 'application/json' };
    options.body = JSON.stringify({ pin });
  }
  const response = await fetch(`${API_BASE}/llm-proxy/api-key/reveal`, withRemoteRevealPinInit(options));
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(extractApiError(data, 'Failed to reveal LLM Proxy API key'));
    err.code = data?.code || null;
    throw err;
  }
  return data;
}

export async function deleteLlmProxyApiKey() {
  const response = await fetch(`${API_BASE}/llm-proxy/api-key`, {
    method: 'DELETE',
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to delete LLM Proxy API key'));
  }
  return data;
}

export async function getRevealPinStatus() {
  const response = await fetch(`${API_BASE}/llm-proxy/reveal-pin`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to get reveal PIN status'));
  }
  return data;
}

export async function setRevealPin(pin) {
  const response = await fetch(`${API_BASE}/llm-proxy/reveal-pin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(extractApiError(data, 'Failed to set reveal PIN'));
    err.code = data?.code || null;
    throw err;
  }
  return data;
}

export async function changeRevealPin(currentPin, newPin) {
  const response = await fetch(`${API_BASE}/llm-proxy/reveal-pin`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ current_pin: currentPin, new_pin: newPin }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(extractApiError(data, 'Failed to change reveal PIN'));
    err.code = data?.code || null;
    throw err;
  }
  return data;
}

export async function disableRevealPin(pin) {
  const response = await fetch(`${API_BASE}/llm-proxy/reveal-pin`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const err = new Error(extractApiError(data, 'Failed to disable reveal PIN'));
    err.code = data?.code || null;
    throw err;
  }
  return data;
}

export async function resetRevealPinLockout() {
  const response = await fetch(`${API_BASE}/llm-proxy/reveal-pin/lockout`, {
    method: 'DELETE',
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to reset reveal PIN lockout'));
  }
  return data;
}

export async function getLlmProxyBuilds(options = {}) {
  const params = new URLSearchParams();
  if (options.diagnostics === false) {
    params.set('diagnostics', '0');
  }
  const qs = params.toString() ? `?${params}` : '';
  const response = await fetch(`${API_BASE}/llm-proxy/builds${qs}`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to load LLM Proxy builds'));
  }
  return data;
}

export async function putLlmProxyBuilds(builds) {
  const response = await fetch(`${API_BASE}/llm-proxy/builds`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ builds }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detailMsg =
      Array.isArray(data.details) && data.details.length ? data.details.join('; ') : null;
    throw new Error(detailMsg || extractApiError(data, 'Failed to save builds'));
  }
  return data;
}

export async function previewLlmProxyBuildModel(model, providerId = null) {
  const response = await fetch(`${API_BASE}/llm-proxy/builds/preview-model`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model,
      ...(providerId ? { provider_id: providerId } : {}),
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Model preview failed'));
  }
  return data;
}

export async function clearProxyLogs(options = {}) {
  const params = new URLSearchParams();
  if (options.autocompleteOnly) {
    params.set('autocomplete_only', '1');
  }
  const response = await fetch(
    `${API_BASE}/proxy-logs${params.toString() ? `?${params}` : ''}`,
    withRemoteRevealPinInit({
      method: 'DELETE',
      cache: 'no-store',
      headers: { 'Cache-Control': 'no-cache' },
    }),
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(extractApiError(err, 'Failed to clear proxy logs'));
  }
  return response.json();
}

export async function getProxyLogs(options = {}) {
  const params = new URLSearchParams();
  const { limit, since_id, from, to, autocompleteOnly } = options;
  if (limit != null) params.set('limit', String(limit));
  if (since_id != null) params.set('since_id', String(since_id));
  if (from != null && from !== '') params.set('from', from);
  if (to != null && to !== '') params.set('to', to);
  if (autocompleteOnly) params.set('autocomplete_only', '1');
  const response = await fetch(
    `${API_BASE}/proxy-logs?${params}`,
    withRemoteRevealPinInit({
      cache: 'no-store',
      headers: { 'Cache-Control': 'no-cache' },
    }),
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throwProxyApiError(data, 'Failed to get proxy logs', response);
  }
  return response.json();
}

export async function getProxyTraceCurrent() {
  const response = await fetch(
    `${API_BASE}/proxy-trace/current`,
    withRemoteRevealPinInit({ method: 'GET' }),
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throwProxyApiError(data, 'Failed to get proxy trace', response);
  }
  return response.json();
}

export async function getProxyTraces(limit = 40) {
  const response = await fetch(
    `${API_BASE}/proxy-traces?limit=${encodeURIComponent(limit)}`,
    withRemoteRevealPinInit({ method: 'GET' }),
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throwProxyApiError(data, 'Failed to get proxy traces', response);
  }
  return response.json();
}

export async function clearProxyTraces() {
  const response = await fetch(
    `${API_BASE}/proxy-traces/clear`,
    withRemoteRevealPinInit({ method: 'POST' }),
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throwProxyApiError(data, 'Failed to clear proxy traces', response);
  }
  return response.json();
}

export async function getProxyJournal(options = {}) {
  const params = new URLSearchParams();
  const { limit, since_id, offset, from, to } = options;
  if (limit != null) params.set('limit', String(limit));
  if (since_id != null) params.set('since_id', String(since_id));
  if (offset != null) params.set('offset', String(offset));
  if (from != null && from !== '') params.set('from', from);
  if (to != null && to !== '') params.set('to', to);
  const response = await fetch(
    `${API_BASE}/proxy-journal?${params}`,
    withRemoteRevealPinInit({ method: 'GET' }),
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(extractApiError(data, 'Failed to load proxy journal'));
  }
  return data;
}

export async function clearProxyJournal() {
  const response = await fetch(
    `${API_BASE}/proxy-journal`,
    withRemoteRevealPinInit({ method: 'DELETE' }),
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(extractApiError(data, 'Failed to clear proxy journal'));
  }
  return data;
}
