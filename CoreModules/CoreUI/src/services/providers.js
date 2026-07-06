import { API_BASE, extractApiError, fetchJsonWithTimeout } from './http.js';

export async function listCustomProviders() {
  const { response, data } = await fetchJsonWithTimeout(`${API_BASE}/providers/custom`, {
    timeoutMs: 15_000,
  });
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to load custom providers'));
  }
  return data;
}

export async function createCustomProvider(payload) {
  const { response, data } = await fetchJsonWithTimeout(`${API_BASE}/providers/custom`, {
    timeoutMs: 30_000,
    fetchOptions: {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    },
  });
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to create provider'));
  }
  return data;
}

export async function updateCustomProvider(providerId, payload) {
  const { response, data } = await fetchJsonWithTimeout(
    `${API_BASE}/providers/custom/${encodeURIComponent(providerId)}`,
    {
      timeoutMs: 30_000,
      fetchOptions: {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      },
    },
  );
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to update provider'));
  }
  return data;
}

export async function deleteCustomProvider(providerId) {
  const { response, data } = await fetchJsonWithTimeout(
    `${API_BASE}/providers/custom/${encodeURIComponent(providerId)}`,
    {
      timeoutMs: 15_000,
      fetchOptions: { method: 'DELETE' },
    },
  );
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to delete provider'));
  }
  return data;
}

export async function testCustomProvider(providerId) {
  const { response, data } = await fetchJsonWithTimeout(
    `${API_BASE}/providers/custom/${encodeURIComponent(providerId)}/test`,
    {
      timeoutMs: 45_000,
      fetchOptions: { method: 'POST' },
    },
  );
  if (!response.ok && response.status !== 502) {
    throw new Error(extractApiError(data, 'Failed to test provider'));
  }
  return { response, data };
}
