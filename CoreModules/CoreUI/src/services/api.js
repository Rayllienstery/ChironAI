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


export async function getVersion() {
  const response = await fetch(`${API_BASE}/version`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(extractApiError(data, 'Failed to get version'));
  }
  return data;
}

export async function getSession({ maxRetries = 3, baseDelayMs = 500, timeoutMs = 1500 } = {}) {
  let url = `${API_BASE}/sessions`;
  try {
    const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(COREUI_SESSION_STORAGE_KEY) : null;
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
      await new Promise(resolve => setTimeout(resolve, baseDelayMs * Math.pow(2, attempt - 1)));
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

export async function getRagStatus() {
  const response = await fetch(`${API_BASE}/rag/status`);
  if (!response.ok) {
    throw new Error('Failed to get RAG status');
  }
  return response.json();
}

export async function getRagCollections() {
  const response = await fetch(`${API_BASE}/rag/collections`);
  let data = {};
  try {
    data = await response.json();
  } catch {
    data = { collections: [], error: 'parse_error' };
  }
  if (!Array.isArray(data.collections)) {
    data.collections = [];
  }
  if (!data.error && !response.ok) {
    data.error = `http_${response.status}`;
  }
  return data;
}

export async function getRagTriggerSettings() {
  const response = await fetch(`${API_BASE}/rag-trigger-settings`);
  if (!response.ok) {
    throw new Error('Failed to get RAG trigger settings');
  }
  return response.json();
}

export async function getRagFrameworkSettings() {
  const response = await fetch(`${API_BASE}/rag-framework-settings`);
  if (!response.ok) {
    throw new Error('Failed to get RAG framework settings');
  }
  return response.json();
}

export async function updateRagFrameworkSettings(settings) {
  const response = await fetch(`${API_BASE}/rag-framework-settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to update RAG framework settings'));
  }
  return response.json();
}

export async function updateRagTriggerSettings(settings) {
  const response = await fetch(`${API_BASE}/rag-trigger-settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to update RAG trigger settings'));
  }
  return response.json();
}

export async function getRagModelSettings() {
  const response = await fetch(`${API_BASE}/rag-model-settings`, {
    method: 'GET',
  });
  if (!response.ok) {
    throw new Error('Failed to get RAG model settings');
  }
  return response.json();
}

/** Proxy/RAG pipeline flags for the GitLab-style diagram (see /api/webui/pipeline-preview). */
export async function getPipelinePreview() {
  const response = await fetch(`${API_BASE}/pipeline-preview`, {
    method: 'GET',
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to load pipeline preview'));
  }
  return response.json();
}

export async function updateRagModelSettings(settings) {
  const response = await fetch(`${API_BASE}/rag-model-settings`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(settings),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to update RAG model settings'));
  }
  return response.json();
}


export async function previewExternalDocs({ library, pipelineName, maxFiles, maxCharsPerFile } = {}) {
  const response = await fetch(`${API_BASE}/testing/external-docs/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      library: (library || '').trim(),
      pipeline_name: pipelineName || undefined,
      max_files: typeof maxFiles === 'number' ? maxFiles : undefined,
      max_chars_per_file: typeof maxCharsPerFile === 'number' ? maxCharsPerFile : undefined,
    }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to preview external docs'));
  }
  return response.json();
}

export async function checkRagTrigger(message) {
  const response = await fetch(`${API_BASE}/rag-trigger-test`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: message || '' }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to check RAG trigger'));
  }
  return response.json();
}

export async function getRagTests(options = {}) {
  const params = new URLSearchParams();
  if (options.platform) params.set('platform', options.platform);
  if (options.framework) params.set('framework', options.framework);
  if (options.difficulty) params.set('difficulty', options.difficulty);
  const qs = params.toString();
  const url = qs ? `${API_BASE}/rag-tests?${qs}` : `${API_BASE}/rag-tests`;
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error('Failed to get RAG tests');
  }
  return response.json();
}

export async function getRagTest(testId) {
  const response = await fetch(`${API_BASE}/rag-tests/${encodeURIComponent(testId)}`);
  if (!response.ok) {
    if (response.status === 404) throw new Error('Test not found');
    throw new Error('Failed to get RAG test');
  }
  return response.json();
}

export async function runRagTests(body) {
  const response = await fetch(`${API_BASE}/rag-tests/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to run RAG tests'));
  }
  const data = await response.json();
  if (response.status === 202) {
    return { job_id: data.job_id };
  }
  return data;
}

export async function getRagTestRunStatus(jobId) {
  const response = await fetch(`${API_BASE}/rag-tests/run/status/${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    if (response.status === 404) throw new Error('Job not found');
    throw new Error('Failed to get run status');
  }
  return response.json();
}

export async function cancelRagTestRun(jobId) {
  const response = await fetch(`${API_BASE}/rag-tests/run/cancel/${encodeURIComponent(jobId)}`, {
    method: 'POST',
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to cancel'));
  }
  return response.json();
}

export async function runRagTesterV2(body) {
  const response = await fetch(`${API_BASE}/rag-tests-v2/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to run Rag Tester V2'));
  }
  const data = await response.json();
  if (response.status === 202) {
    return { job_id: data.job_id, ...data };
  }
  return data;
}

export async function getRagTesterV2RunStatus(jobId) {
  const response = await fetch(`${API_BASE}/rag-tests-v2/run/status/${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    if (response.status === 404) throw new Error('Job not found');
    throw new Error('Failed to get Rag Tester V2 run status');
  }
  return response.json();
}

export async function cancelRagTesterV2Run(jobId) {
  const response = await fetch(`${API_BASE}/rag-tests-v2/run/cancel/${encodeURIComponent(jobId)}`, {
    method: 'POST',
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to cancel Rag Tester V2 run'));
  }
  return response.json();
}

export async function getRagTestRuns(options = {}) {
  const params = new URLSearchParams();
  if (options.limit != null) params.set('limit', String(options.limit));
  if (options.offset != null) params.set('offset', String(options.offset));
  if (options.provider_id) params.set('provider_id', options.provider_id);
  if (options.model) params.set('model', options.model);
  if (options.from_date) params.set('from_date', options.from_date);
  if (options.to_date) params.set('to_date', options.to_date);
  if (options.status) params.set('status', options.status);
  const qs = params.toString();
  const url = qs ? `${API_BASE}/rag-tests/runs?${qs}` : `${API_BASE}/rag-tests/runs`;
  const response = await fetch(url);
  if (!response.ok) throw new Error('Failed to get run history');
  return response.json();
}

export async function deleteRagTestRuns(body) {
  const response = await fetch(`${API_BASE}/rag-tests/runs`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body || {}),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to delete run history'));
  }
  return response.json();
}

export async function getRagTestRunsSummary(options = {}) {
  const params = new URLSearchParams();
  if (options.limit != null) params.set('limit', String(options.limit));
  if (options.provider_id) params.set('provider_id', options.provider_id);
  if (options.model) params.set('model', options.model);
  if (options.from_date) params.set('from_date', options.from_date);
  if (options.to_date) params.set('to_date', options.to_date);
  const qs = params.toString();
  const url = qs ? `${API_BASE}/rag-tests/runs/summary?${qs}` : `${API_BASE}/rag-tests/runs/summary`;
  const response = await fetch(url);
  if (!response.ok) throw new Error('Failed to get runs summary');
  return response.json();
}

export async function getRagTestRun(runId) {
  const response = await fetch(`${API_BASE}/rag-tests/runs/${encodeURIComponent(runId)}`);
  if (!response.ok) {
    if (response.status === 404) throw new Error('Run not found');
    throw new Error('Failed to get run');
  }
  return response.json();
}

/**
 * Export a run as JSON or CSV and trigger download.
 * @param {string} runId
 * @param {'json'|'csv'} format
 * @param {string} [suggestedFilename] - optional filename (without extension)
 */
export async function exportRagTestRun(runId, format, suggestedFilename) {
  const url = `${API_BASE}/rag-tests/runs/${encodeURIComponent(runId)}/export?format=${format === 'csv' ? 'csv' : 'json'}`;
  const response = await fetch(url);
  if (!response.ok) {
    if (response.status === 404) throw new Error('Run not found');
    throw new Error('Failed to export run');
  }
  const blob = await response.blob();
  const disp = response.headers.get('Content-Disposition');
  let filename = suggestedFilename || `rag-test-run-${runId}`;
  if (disp) {
    const m = disp.match(/filename="?([^"]+)"?/);
    if (m) filename = m[1];
  }
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
  URL.revokeObjectURL(a.href);
}

export async function createRagTest(body) {
  const response = await fetch(`${API_BASE}/rag-tests`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to create RAG test'));
  }
  return response.json();
}

export async function updateRagTest(testId, body) {
  const response = await fetch(`${API_BASE}/rag-tests/${encodeURIComponent(testId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to update RAG test'));
  }
  return response.json();
}

export async function deleteRagTest(testId) {
  const response = await fetch(`${API_BASE}/rag-tests/${encodeURIComponent(testId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to delete RAG test'));
  }
}

export async function getRagKeywordCollections() {
  const response = await fetch(`${API_BASE}/rag-keyword-collections`);
  if (!response.ok) {
    throw new Error('Failed to get RAG keyword collections');
  }
  return response.json();
}

export async function saveRagKeywordCollections(payload) {
  const response = await fetch(`${API_BASE}/rag-keyword-collections`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(extractApiError(err, 'Failed to save RAG keyword collections'));
  }
  return response.json();
}

export async function deleteRagKeywordCollection(collectionId) {
  const response = await fetch(`${API_BASE}/rag-keyword-collections/${encodeURIComponent(collectionId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(extractApiError(err, 'Failed to delete collection'));
  }
  return response.json();
}

export async function startRag() {
  const response = await fetch(`${API_BASE}/rag/start`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to start RAG server'));
  }
  return response.json();
}

export async function stopRag() {
  const response = await fetch(`${API_BASE}/rag/stop`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, 'Failed to stop RAG server'));
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
  const response = await fetch(`${API_BASE}/prompts/trash/${encodeURIComponent(trashName)}/restore`, {
    method: 'POST',
  });
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
