/**
 * @typedef {import('./api.types').paths} ApiPaths
 */

import {
  API_BASE,
  COREUI_SESSION_STORAGE_KEY,
  extractApiError,
  fetchJsonWithTimeout,
} from './http.js';

export {
  getLlmProxyStatus,
  getLlmProxyApiKeyStatus,
  generateLlmProxyApiKey,
  revealLlmProxyApiKey,
  deleteLlmProxyApiKey,
  getLlmProxyBuilds,
  putLlmProxyBuilds,
  previewLlmProxyBuildModel,
  clearProxyLogs,
  getProxyLogs,
  getProxyTraceCurrent,
  getProxyTraces,
  clearProxyTraces,
  getProxyJournal,
  clearProxyJournal,
} from './proxy.js';

export {
  getIndexerTesterSources,
  getIndexerTesterFiles,
  getIndexerTesterFileDetail,
  evaluateIndexerWithLlm,
  startIndexerTesterEvaluateBatch,
  getIndexerTesterEvaluateBatchStatus,
  detectBatchEvalPatterns,
  getMdPipelines,
  getMdPipeline,
  saveMdPipeline,
  deleteMdPipeline,
  previewMdPipeline,
  getCrawlerSources,
  getCrawlerSourcePages,
  createCollection,
  getCreateCollectionStatus,
  cancelCreateCollection,
  crawlSource,
  getCrawlStatus,
  addCrawlerSource,
  getCrawlerSource,
  updateCrawlerSource,
} from './crawler.js';

export {
  getProviderCatalog,
  getExtensionTabs,
  getExtensionTab,
  refreshExtensionTab,
  runExtensionTabAction,
  getExtensionRegistry,
  getExtensionInstalled,
  getExtensionProviders,
  getExtensionUiPayload,
  getExtensionDetails,
  installExtension,
  installExtensionTarget,
  removeExtension,
  enableExtension,
  disableExtension,
  updateExtensionDocker,
  restartExtensionSandbox,
  killExtensionSandbox,
} from './extensions.js';

export {
  listCustomProviders,
  createCustomProvider,
  updateCustomProvider,
  deleteCustomProvider,
  testCustomProvider,
} from './providers.js';

export {
  getRagStatus,
  getRagCollections,
  getRagTriggerSettings,
  getRagFrameworkSettings,
  updateRagFrameworkSettings,
  updateRagTriggerSettings,
  getRagModelSettings,
  getPipelinePreview,
  updateRagModelSettings,
  previewExternalDocs,
  checkRagTrigger,
  getRagTests,
  getRagTest,
  runRagTests,
  getRagTestRunStatus,
  cancelRagTestRun,
  runRagTesterV2,
  getRagTesterV2RunStatus,
  cancelRagTesterV2Run,
  getRagTestRuns,
  deleteRagTestRuns,
  getRagTestRunsSummary,
  getRagTestRun,
  exportRagTestRun,
  createRagTest,
  updateRagTest,
  deleteRagTest,
  getRagKeywordCollections,
  saveRagKeywordCollections,
  deleteRagKeywordCollection,
  startRag,
  stopRag,
} from './rag.js';

export async function getVersion() {
  const response = await fetch(`${API_BASE}/version`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to get version'));
  }
  return data;
}

export async function getHelpArticles() {
  const response = await fetch(`${API_BASE}/help`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to list help articles'));
  }
  return data;
}

export async function getHelpArticle(slug) {
  const normalized = encodeURIComponent(String(slug || '').trim());
  const response = await fetch(`${API_BASE}/help/${normalized}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to load help article'));
  }
  return data;
}

export async function searchHelpArticles(query) {
  const params = new URLSearchParams({ q: String(query || '').trim() });
  const response = await fetch(`${API_BASE}/help/search?${params}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to search help'));
  }
  return data;
}

export async function getSession({ maxRetries = 3, baseDelayMs = 500, timeoutMs = 1500 } = {}) {
  let url = `${API_BASE}/sessions`;
  try {
    const stored =
      typeof localStorage !== 'undefined' ? localStorage.getItem(COREUI_SESSION_STORAGE_KEY) : null;
    if (stored && String(stored).trim()) {
      const params = new URLSearchParams({ session_id: String(stored).trim() });
      url = `${API_BASE}/sessions?${params}`;
    }
  } catch {
    // localStorage unavailable (e.g. private mode)
  }

  let lastError;
  for (let attempt = 0; attempt < maxRetries; attempt++) {
    if (attempt > 0) {
      // Exponential backoff: 500ms, 1s, 2s, 4s, 8s
      await new Promise((resolve) => setTimeout(resolve, baseDelayMs * Math.pow(2, attempt - 1)));
    }
    try {
      const { response, data: session } = await fetchJsonWithTimeout(url, {
        timeoutMs,
        fetchOptions: { method: 'GET' },
      });
      if (!response.ok) {
        throw new Error(`Failed to get session: ${response.status}`);
      }
      try {
        if (session && session.id && typeof localStorage !== 'undefined') {
          localStorage.setItem(COREUI_SESSION_STORAGE_KEY, String(session.id));
        }
      } catch {
        // ignore
      }
      return session;
    } catch (e) {
      lastError = e;
      // Continue to next retry
    }
  }
  throw lastError;
}

export async function getPrompts() {
  const response = await fetch(`${API_BASE}/prompts`);
  if (!response.ok) {
    throw new Error('Failed to get prompts');
  }
  const data = await response.json();
  return data;
}

export async function getModelSettings() {
  const response = await fetch(`${API_BASE}/model-settings`);
  if (!response.ok) {
    throw new Error('Failed to get model settings');
  }
  return response.json();
}

export async function updateModelSettings(settings) {
  const response = await fetch(`${API_BASE}/model-settings`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(settings),
  });
  if (!response.ok) {
    throw new Error('Failed to update model settings');
  }
  return response.json();
}

export async function getTesterSettings(sessionId) {
  const response = await fetch(`${API_BASE}/tester-settings?session_id=${sessionId}`);
  if (!response.ok) {
    throw new Error('Failed to get tester settings');
  }
  return response.json();
}

export async function updateTesterSettings(sessionId, settings) {
  const response = await fetch(`${API_BASE}/tester-settings`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ session_id: sessionId, ...settings }),
  });
  if (!response.ok) {
    throw new Error('Failed to update tester settings');
  }
  return response.json();
}

export async function testerChat(sessionId, messages, options = {}) {
  const response = await fetch(`${API_BASE}/tester/chat`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      session_id: sessionId,
      messages,
      ...options,
    }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(extractApiError(error, 'Chat request failed'));
  }
  return response.json();
}

export async function testerPromptPreview(options = {}) {
  const response = await fetch(`${API_BASE}/tester/prompt-preview`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(options),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to get prompt preview'));
  }
  return response.json();
}

export async function getLogs(sessionId, options = {}) {
  const params = new URLSearchParams({
    session_id: sessionId,
    ...options,
  });
  const response = await fetch(`${API_BASE}/logs?${params}`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  if (!response.ok) {
    throw new Error('Failed to get logs');
  }
  return response.json();
}

export async function getDependencies() {
  const response = await fetch(`${API_BASE}/dependencies`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(extractApiError(err, 'Failed to get dependencies'));
  }
  return response.json();
}

export async function checkDependencyUpdates() {
  const response = await fetch(`${API_BASE}/dependencies/check-updates`, {
    method: 'POST',
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to check dependency updates'));
  }
  return data;
}

export async function updateDependencies() {
  const response = await fetch(`${API_BASE}/dependencies/update`, {
    method: 'POST',
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to update dependencies'));
  }
  return data;
}

export async function getDependencyJob(jobId) {
  const response = await fetch(`${API_BASE}/dependencies/jobs/${encodeURIComponent(jobId)}`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to get dependency job'));
  }
  return data;
}

export async function getCoreuiNotifications(sessionId, options = {}) {
  const params = new URLSearchParams({ session_id: sessionId });
  if (options.limit != null) params.set('limit', String(options.limit));
  if (options.includeDismissed === false) {
    params.set('include_dismissed', 'false');
  }
  const response = await fetch(`${API_BASE}/notifications?${params}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(extractApiError(err, 'Failed to get notifications'));
  }
  return response.json();
}

export async function createCoreuiNotification(sessionId, payload) {
  const response = await fetch(`${API_BASE}/notifications`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      session_id: sessionId,
      kind: payload.kind || 'event',
      source: payload.source,
      title: payload.title,
      message: payload.message ?? '',
      metadata: payload.metadata,
      aggregation_key: payload.aggregation_key ?? null,
      is_console_error: payload.is_console_error || false,
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to create notification'));
  }
  return data;
}

export async function dismissCoreuiNotification(sessionId, notificationId) {
  const response = await fetch(`${API_BASE}/notifications/${notificationId}/dismiss`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to dismiss notification'));
  }
  return data;
}

export async function clearCoreuiNotifications(sessionId) {
  const response = await fetch(`${API_BASE}/notifications/clear`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to clear notifications'));
  }
  return data;
}

export async function clearLogs(sessionId, options = {}) {
  const params = new URLSearchParams({ session_id: sessionId });
  if (options.includeSystem === false) {
    params.set('include_system', '0');
  }
  const response = await fetch(`${API_BASE}/logs?${params}`, {
    method: 'DELETE',
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(extractApiError(err, 'Failed to clear logs'));
  }
  return response.json();
}

export async function getSettings() {
  const response = await fetch(`${API_BASE}/settings`);
  if (!response.ok) {
    throw new Error('Failed to get settings');
  }
  return response.json();
}

export async function updateSettings(settings) {
  const response = await fetch(`${API_BASE}/settings`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(settings),
  });
  if (!response.ok) {
    throw new Error('Failed to update settings');
  }
  return response.json();
}

export async function getDashboardMetrics() {
  const response = await fetch(`${API_BASE}/dashboard-metrics`);
  if (!response.ok) {
    throw new Error('Failed to get dashboard metrics');
  }
  return response.json();
}

export async function stopServer() {
  const response = await fetch(`${API_BASE}/server/stop`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to stop WebUI server'));
  }
  return response.json();
}

export async function getPromptContent(name) {
  const response = await fetch(`${API_BASE}/prompts/${encodeURIComponent(name)}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to get prompt content'));
  }
  return response.json();
}

export async function createPrompt({ sourceName, name, content }) {
  const response = await fetch(`${API_BASE}/prompts`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ source_name: sourceName, name, content }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to create prompt'));
  }
  return response.json();
}

export async function updatePrompt(name, { newName, content }) {
  const response = await fetch(`${API_BASE}/prompts/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ new_name: newName, content }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to update prompt'));
  }
  return response.json();
}

export async function deletePrompt(name) {
  const response = await fetch(`${API_BASE}/prompts/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to delete prompt'));
  }
  return response.json();
}

export async function getTrashPrompts() {
  const response = await fetch(`${API_BASE}/prompts/trash`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to get trash prompts'));
  }
  return response.json();
}

export async function getTrashPromptContent(trashName) {
  const response = await fetch(`${API_BASE}/prompts/trash/${encodeURIComponent(trashName)}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to get trash prompt content'));
  }
  return response.json();
}

export async function updateTrashPrompt(trashName, content) {
  const response = await fetch(`${API_BASE}/prompts/trash/${encodeURIComponent(trashName)}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ content }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to update trash prompt'));
  }
  return response.json();
}

export async function restorePrompt(trashName) {
  const response = await fetch(
    `${API_BASE}/prompts/trash/${encodeURIComponent(trashName)}/restore`,
    {
      method: 'POST',
    },
  );
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to restore prompt'));
  }
  return response.json();
}

export async function clearTrash() {
  const response = await fetch(`${API_BASE}/prompts/trash`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to clear trash'));
  }
  return response.json();
}

export async function getDockerStatus() {
  const response = await fetch(`${API_BASE}/docker/status`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(extractApiError(data, 'Failed to load Docker status'));
  }
  return data;
}

export async function getDockerContainers() {
  const response = await fetch(`${API_BASE}/docker/containers`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(extractApiError(data, 'Failed to load Docker containers'));
  }
  return data;
}

export async function getDockerImages() {
  const response = await fetch(`${API_BASE}/docker/images`, {
    cache: 'no-store',
    headers: { 'Cache-Control': 'no-cache' },
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(extractApiError(data, 'Failed to load Docker images'));
  }
  return data;
}

export function subscribeDockerEvents(onEvent, onError) {
  if (typeof EventSource === 'undefined') return null;
  const source = new EventSource(`${API_BASE}/docker/events`);
  source.addEventListener('docker', (event) => {
    try {
      onEvent?.(JSON.parse(event.data || '{}'));
    } catch (e) {
      onError?.(e);
    }
  });
  source.onerror = (event) => {
    onError?.(event);
  };
  return source;
}

async function dockerJsonAction(path, body = {}, method = 'POST') {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || data.ok === false) {
    throw new Error(data.details || extractApiError(data, 'Docker action failed'));
  }
  return data;
}

export async function checkDockerImageUpdate(image) {
  return dockerJsonAction('/docker/images/check-update', { image });
}

export async function updateDockerImage(image) {
  return dockerJsonAction('/docker/images/update', { image });
}

export async function startDockerContainer(container) {
  return dockerJsonAction('/docker/containers/start', { container });
}

export async function stopDockerContainer(container) {
  return dockerJsonAction('/docker/containers/stop', { container });
}

export async function removeDockerContainer(container, force = false) {
  return dockerJsonAction('/docker/containers', { container, force, confirm: container }, 'DELETE');
}

export async function removeDockerImage(image, force = false) {
  return dockerJsonAction('/docker/images', { image, force, confirm: image }, 'DELETE');
}

/**
 * Fetch the startup timing report from the backend.
 * Returns phases recorded by Python during process startup plus any
 * browser timing that has been submitted via postBrowserTiming().
 *
 * @returns {Promise<object>}
 */
export async function getStartupPerformance() {
  const { response, data } = await fetchJsonWithTimeout(`${API_BASE}/performance/startup`, {
    timeoutMs: 8000,
    fetchOptions: { method: 'GET' },
  });
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to fetch startup performance'));
  }
  return data;
}

/**
 * Post browser Navigation Timing data so it can be merged into the startup report.
 * Call once after the app is fully interactive.
 *
 * @param {object} payload  - Timing data (e.g. window.performance.timing + custom milestones)
 * @returns {Promise<{ok: boolean}>}
 */
export async function postBrowserTiming(payload) {
  const response = await fetch(`${API_BASE}/performance/browser-timing`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to post browser timing'));
  }
  return response.json();
}
