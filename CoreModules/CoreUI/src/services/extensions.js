import { API_BASE, extractApiError, fetchJsonWithTimeout } from './http.js';

export async function getProviderCatalog(capability = '') {
  const params = new URLSearchParams();
  if (capability) params.set('capability', capability);
  const response = await fetch(
    `${API_BASE}/providers/catalog${params.toString() ? `?${params}` : ''}`,
  );
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to get provider catalog'));
  }
  return data;
}

export async function getExtensionTabs() {
  const response = await fetch(`${API_BASE}/extensions/tabs`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to load extension tabs'));
  }
  return data;
}

export async function getExtensionTab(extensionId) {
  const { response, data } = await fetchJsonWithTimeout(
    `${API_BASE}/extensions/${encodeURIComponent(extensionId)}/tab`,
    { timeoutMs: 5_000 },
  );
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to load extension tab'));
  }
  return data;
}

export async function refreshExtensionTab(extensionId) {
  const { response, data } = await fetchJsonWithTimeout(
    `${API_BASE}/extensions/${encodeURIComponent(extensionId)}/tab/refresh`,
    {
      timeoutMs: 5_000,
      fetchOptions: { method: 'POST' },
    },
  );
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to refresh extension tab'));
  }
  return data;
}

export async function runExtensionTabAction(extensionId, actionId, payload = {}, options = {}) {
  const timeoutMs = typeof options.timeoutMs === 'number' ? options.timeoutMs : 30_000;
  const { response, data } = await fetchJsonWithTimeout(
    `${API_BASE}/extensions/${encodeURIComponent(extensionId)}/actions/${encodeURIComponent(actionId)}`,
    {
      timeoutMs,
      fetchOptions: {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload || {}),
      },
    },
  );
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Extension action failed'));
  }
  return data;
}

export async function getExtensionRegistry({ forceRefresh = false } = {}) {
  const url = forceRefresh
    ? `${API_BASE}/extensions/registry?refresh=1`
    : `${API_BASE}/extensions/registry`;
  const response = await fetch(url);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to load extension registry'));
  }
  return response.json();
}

export async function getExtensionInstalled({ dockerVersions = true } = {}) {
  const params = new URLSearchParams();
  if (dockerVersions === false) params.set('docker_versions', '0');
  const qs = params.toString() ? `?${params}` : '';
  const response = await fetch(`${API_BASE}/extensions/installed${qs}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to load installed extensions'));
  }
  return response.json();
}

export async function getExtensionProviders() {
  const response = await fetch(`${API_BASE}/extensions/providers`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to load extension providers'));
  }
  return response.json();
}

export async function getExtensionUiPayload() {
  const response = await fetch(`${API_BASE}/extensions/ui`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to load extension UI payload'));
  }
  return response.json();
}

export async function getExtensionDetails(extensionId, ref = null) {
  const query = ref ? `?ref=${encodeURIComponent(ref)}` : '';
  const response = await fetch(`${API_BASE}/extensions/${encodeURIComponent(extensionId)}/details${query}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to load extension details'));
  }
  return response.json();
}

async function postExtensionAction(path, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Extension action failed'));
  }
  return data;
}

export async function installExtension(extensionId, version = null) {
  return postExtensionAction('/extensions/install', { extension_id: extensionId, version });
}

export async function installExtensionTarget(extensionId, target = {}) {
  return postExtensionAction('/extensions/install', { extension_id: extensionId, target });
}

export async function removeExtension(extensionId) {
  return postExtensionAction('/extensions/remove', { extension_id: extensionId });
}

export async function enableExtension(extensionId) {
  return postExtensionAction('/extensions/enable', { extension_id: extensionId });
}

export async function disableExtension(extensionId) {
  return postExtensionAction('/extensions/disable', { extension_id: extensionId });
}

export async function updateExtensionDocker(extensionIds, { timeoutMs = 600000, skipImagePull = false } = {}) {
  const ids = Array.isArray(extensionIds) ? extensionIds : [extensionIds];
  const { response, data } = await fetchJsonWithTimeout(`${API_BASE}/extensions/docker/update`, {
    timeoutMs,
    fetchOptions: {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ extension_ids: ids, skip_image_pull: Boolean(skipImagePull) }),
    },
  });
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to update extension container'));
  }
  return data;
}

export async function restartExtensionSandbox(extensionId) {
  return postExtensionAction(`/extensions/${encodeURIComponent(extensionId)}/sandbox/restart`, {});
}

export async function killExtensionSandbox(extensionId) {
  return postExtensionAction(`/extensions/${encodeURIComponent(extensionId)}/sandbox/kill`, {});
}

