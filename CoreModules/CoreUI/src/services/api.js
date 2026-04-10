const API_BASE = '/api/webui';

export async function getSession() {
  const response = await fetch(`${API_BASE}/sessions`, {
    method: 'GET',
  });
  if (!response.ok) {
    throw new Error('Failed to get session');
  }
  return response.json();
}

/** @returns {Promise<Array<{ id: string, name: string }>>} models array (not wrapped in { models }) */
export async function getModels() {
  const response = await fetch(`${API_BASE}/models`);
  if (!response.ok) {
    throw new Error('Failed to get models');
  }
  const data = await response.json();
  return data.models ?? [];
}

export async function getPrompts() {
  const response = await fetch(`${API_BASE}/prompts`);
  if (!response.ok) {
    throw new Error('Failed to get prompts');
  }
  const data = await response.json();
  return data;
}

export async function getConfig() {
  const response = await fetch(`${API_BASE}/config`);
  if (!response.ok) {
    throw new Error('Failed to get config');
  }
  return response.json();
}

export async function getModelSettings() {
  const response = await fetch(`${API_BASE}/model-settings`);
  if (!response.ok) {
    throw new Error('Failed to get model settings');
  }
  return response.json();
}

export async function getLlmProxyStatus() {
  const response = await fetch(`${API_BASE}/llm-proxy/status`);
  if (!response.ok) {
    throw new Error('Failed to get LLM Proxy status');
  }
  return response.json();
}

export async function getLlmProxyBuilds() {
  const response = await fetch(`${API_BASE}/llm-proxy/builds`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || 'Failed to load LLM Proxy builds');
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
    throw new Error(detailMsg || data.error || 'Failed to save builds');
  }
  return data;
}

export async function previewLlmProxyBuildModel(model) {
  const response = await fetch(`${API_BASE}/llm-proxy/builds/preview-model`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || 'Model preview failed');
  }
  return data;
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
    throw new Error(error.error || 'Chat request failed');
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
    throw new Error(error.error || 'Failed to get prompt preview');
  }
  return response.json();
}

export async function getLogs(sessionId, options = {}) {
  const params = new URLSearchParams({
    session_id: sessionId,
    ...options,
  });
  const response = await fetch(`${API_BASE}/logs?${params}`);
  if (!response.ok) {
    throw new Error('Failed to get logs');
  }
  return response.json();
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
    throw new Error(err.error || 'Failed to get notifications');
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
      is_console_error: payload.is_console_error || false,
    }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || 'Failed to create notification');
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
    throw new Error(data.error || 'Failed to dismiss notification');
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
    throw new Error(data.error || 'Failed to clear notifications');
  }
  return data;
}

export async function clearLogs(sessionId, options = {}) {
  const params = new URLSearchParams({ session_id: sessionId });
  if (options.includeSystem === false) {
    params.set('include_system', '0');
  }
  const response = await fetch(`${API_BASE}/logs?${params}`, { method: 'DELETE' });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || 'Failed to clear logs');
  }
  return response.json();
}

export async function clearProxyLogs(options = {}) {
  const params = new URLSearchParams();
  if (options.autocompleteOnly) {
    params.set('autocomplete_only', '1');
  }
  const response = await fetch(
    `${API_BASE}/proxy-logs${params.toString() ? `?${params}` : ''}`,
    { method: 'DELETE' }
  );
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || 'Failed to clear proxy logs');
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
  const response = await fetch(`${API_BASE}/proxy-logs?${params}`);
  if (!response.ok) {
    throw new Error('Failed to get proxy logs');
  }
  return response.json();
}

export async function getProxyTraceCurrent() {
  const response = await fetch(`${API_BASE}/proxy-trace/current`, {
    method: 'GET',
  });
  if (!response.ok) {
    throw new Error('Failed to get proxy trace');
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
    throw new Error(data.error || 'Failed to update RAG framework settings');
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
    throw new Error(data.error || 'Failed to update RAG trigger settings');
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
    throw new Error(data.error || 'Failed to load pipeline preview');
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
    throw new Error(data.error || 'Failed to update RAG model settings');
  }
  return response.json();
}

export async function getIndexerTesterSources() {
  const response = await fetch(`${API_BASE}/crawler/indexer-tester/sources`);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to get Indexer Tester sources');
  }
  return response.json();
}

export async function getIndexerTesterFiles(sourceId, options = {}) {
  const params = new URLSearchParams();
  if (options.sortBy) params.set('sort', options.sortBy);
  if (options.order) params.set('order', options.order);
  const query = params.toString();
  const response = await fetch(
    `${API_BASE}/crawler/indexer-tester/sources/${encodeURIComponent(sourceId)}/files${query ? `?${query}` : ''}`,
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to get Indexer Tester files');
  }
  return response.json();
}

export async function getIndexerTesterFileDetail(sourceId, filename) {
  const response = await fetch(
    `${API_BASE}/crawler/indexer-tester/sources/${encodeURIComponent(sourceId)}/files/${encodeURIComponent(
      filename,
    )}`,
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to get Indexer Tester file detail');
  }
  return response.json();
}

export async function evaluateIndexerWithLlm(sourceMd, processedMd, model, pageMeta = null, limits = null) {
  const body = {
    source_md: sourceMd,
    processed_md: processedMd,
    model: model || undefined,
  };
  if (pageMeta != null && typeof pageMeta === 'object') {
    body.page_meta = pageMeta;
  }
  if (limits != null && typeof limits === 'object') {
    if (typeof limits.original_max_chars === 'number') body.original_max_chars = limits.original_max_chars;
    if (typeof limits.processed_max_chars === 'number') body.processed_max_chars = limits.processed_max_chars;
    if (typeof limits.removed_max_chars === 'number') body.removed_max_chars = limits.removed_max_chars;
  }
  const response = await fetch(`${API_BASE}/crawler/indexer-tester/evaluate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const text = await response.text();
    let data = {};
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: text ? text.slice(0, 300) : response.statusText };
    }
    throw new Error(data.error || 'Evaluate failed');
  }
  return response.json();
}

export async function startIndexerTesterEvaluateBatch({
  sourceId,
  model,
  count,
  original_max_chars,
  processed_max_chars,
  removed_max_chars,
}) {
  const body = {
    source_id: sourceId,
    model: model || undefined,
    count: Number(count) || 0,
  };
  if (typeof original_max_chars === 'number') body.original_max_chars = original_max_chars;
  if (typeof processed_max_chars === 'number') body.processed_max_chars = processed_max_chars;
  if (typeof removed_max_chars === 'number') body.removed_max_chars = removed_max_chars;
  const response = await fetch(`${API_BASE}/crawler/indexer-tester/evaluate-batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to start batch evaluation');
  }
  return response.json();
}

export async function getIndexerTesterEvaluateBatchStatus(jobId) {
  const response = await fetch(
    `${API_BASE}/crawler/indexer-tester/evaluate-batch/status/${encodeURIComponent(jobId)}`,
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to get batch status');
  }
  return response.json();
}

export async function detectBatchEvalPatterns(results, model) {
  const response = await fetch(
    `${API_BASE}/crawler/indexer-tester/evaluate-batch/detect-patterns`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        results: results || [],
        model: model || undefined,
      }),
    },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to detect patterns');
  }
  return response.json();
}

// MD Pipelines (config-driven markdown cleanup for RAG)
export async function getMdPipelines() {
  const response = await fetch(`${API_BASE}/crawler/md-pipelines`);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to list MD pipelines');
  }
  return response.json();
}

export async function getMdPipeline(name) {
  const response = await fetch(
    `${API_BASE}/crawler/md-pipelines/${encodeURIComponent(name)}`,
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || `Failed to get pipeline ${name}`);
  }
  return response.json();
}

export async function saveMdPipeline(name, pipeline) {
  const response = await fetch(
    `${API_BASE}/crawler/md-pipelines/${encodeURIComponent(name)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(pipeline),
    },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to save pipeline');
  }
  return response.json();
}

export async function deleteMdPipeline(name) {
  const response = await fetch(
    `${API_BASE}/crawler/md-pipelines/${encodeURIComponent(name)}`,
    { method: 'DELETE' },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to delete pipeline');
  }
  return response.json();
}

export async function previewMdPipeline(pipelineName, sourceId, filename) {
  const response = await fetch(`${API_BASE}/crawler/md-pipelines/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pipeline_name: pipelineName || undefined,
      source_id: sourceId,
      filename,
    }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to preview pipeline');
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
    throw new Error(data.error || 'Failed to preview external docs');
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
    throw new Error(data.error || 'Failed to check RAG trigger');
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
    throw new Error(data.error || 'Failed to run RAG tests');
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
    throw new Error(data.error || 'Failed to cancel');
  }
  return response.json();
}

export async function getRagTestRuns(options = {}) {
  const params = new URLSearchParams();
  if (options.limit != null) params.set('limit', String(options.limit));
  if (options.offset != null) params.set('offset', String(options.offset));
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

export async function getRagTestRunsSummary(options = {}) {
  const params = new URLSearchParams();
  if (options.limit != null) params.set('limit', String(options.limit));
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
    throw new Error(data.error || 'Failed to create RAG test');
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
    throw new Error(data.error || 'Failed to update RAG test');
  }
  return response.json();
}

export async function deleteRagTest(testId) {
  const response = await fetch(`${API_BASE}/rag-tests/${encodeURIComponent(testId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to delete RAG test');
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
    throw new Error(err.error || 'Failed to save RAG keyword collections');
  }
  return response.json();
}

export async function deleteRagKeywordCollection(collectionId) {
  const response = await fetch(`${API_BASE}/rag-keyword-collections/${encodeURIComponent(collectionId)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || 'Failed to delete collection');
  }
  return response.json();
}

export async function startRag() {
  const response = await fetch(`${API_BASE}/rag/start`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to start RAG server');
  }
  return response.json();
}

export async function stopRag() {
  const response = await fetch(`${API_BASE}/rag/stop`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to stop RAG server');
  }
  return response.json();
}

export async function getOllamaStatus() {
  const response = await fetch(`${API_BASE}/ollama/status`);
  if (!response.ok) {
    throw new Error('Failed to get Ollama status');
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

export async function startOllama() {
  const response = await fetch(`${API_BASE}/ollama/start`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to start Ollama server');
  }
  return response.json();
}

export async function stopOllama() {
  const response = await fetch(`${API_BASE}/ollama/stop`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to stop Ollama server');
  }
  return response.json();
}

export async function getOllamaLibrary() {
  const response = await fetch(`${API_BASE}/ollama/library`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || 'Failed to load Ollama library');
  }
  return data;
}

export async function patchOllamaHidden({ add = [], remove = [] } = {}) {
  const response = await fetch(`${API_BASE}/ollama/hidden`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ add, remove }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || 'Failed to update hidden models');
  }
  return data;
}

export async function showOllamaModel(model) {
  const response = await fetch(`${API_BASE}/ollama/show`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || 'Failed to load model details');
  }
  return data;
}

export async function deleteOllamaModel(model) {
  const response = await fetch(`${API_BASE}/ollama/delete`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || 'Failed to delete model');
  }
  return data;
}

/**
 * Stream NDJSON progress from POST /ollama/pull.
 * @param {{ model: string, insecure?: boolean, onLine: (obj: object) => void, signal?: AbortSignal }} opts
 */
export async function pullOllamaModel({ model, insecure = false, onLine, signal }) {
  const response = await fetch(`${API_BASE}/ollama/pull`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model, insecure: Boolean(insecure) }),
    signal,
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || 'Pull request failed');
  }
  const reader = response.body?.getReader();
  if (!reader) {
    throw new Error('No response body');
  }
  const dec = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let idx;
    while ((idx = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, idx).trim();
      buf = buf.slice(idx + 1);
      if (!line) continue;
      try {
        onLine(JSON.parse(line));
      } catch {
        /* ignore malformed line */
      }
    }
  }
  const tail = buf.trim();
  if (tail) {
    try {
      onLine(JSON.parse(tail));
    } catch {
      /* ignore */
    }
  }
}

export async function getOpenWebUiStatus() {
  const response = await fetch(`${API_BASE}/open-webui/status`);
  const data = await response.json().catch(() => ({}));
  const base = {
    running: Boolean(data.running),
    url: data.url ?? null,
    http_status: data.http_status,
    http_error: data.http_error,
    error: data.error,
  };
  if (!response.ok) {
    return { ...base, running: false };
  }
  return base;
}

export async function getOpenWebUiConfig() {
  const response = await fetch(`${API_BASE}/open-webui/config`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.error || 'Failed to load Open WebUI configuration');
  }
  if (data.error) {
    throw new Error(data.error);
  }
  return data;
}

export async function startOpenWebUi() {
  const response = await fetch(`${API_BASE}/open-webui/start`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const msg =
      (typeof error.output === 'string' && error.output) ||
      error.error ||
      'Failed to start Open WebUI';
    throw new Error(msg);
  }
  return response.json();
}

export async function stopOpenWebUi() {
  const response = await fetch(`${API_BASE}/open-webui/stop`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    const msg =
      (typeof error.output === 'string' && error.output) ||
      error.error ||
      'Failed to stop Open WebUI';
    throw new Error(msg);
  }
  return response.json();
}

export async function stopServer() {
  const response = await fetch(`${API_BASE}/server/stop`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to stop WebUI server');
  }
  return response.json();
}

export async function getPromptContent(name) {
  const response = await fetch(`${API_BASE}/prompts/${encodeURIComponent(name)}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to get prompt content');
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
    throw new Error(error.error || 'Failed to create prompt');
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
    throw new Error(error.error || 'Failed to update prompt');
  }
  return response.json();
}

export async function deletePrompt(name) {
  const response = await fetch(`${API_BASE}/prompts/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to delete prompt');
  }
  return response.json();
}

export async function getTrashPrompts() {
  const response = await fetch(`${API_BASE}/prompts/trash`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to get trash prompts');
  }
  return response.json();
}

export async function getTrashPromptContent(trashName) {
  const response = await fetch(`${API_BASE}/prompts/trash/${encodeURIComponent(trashName)}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to get trash prompt content');
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
    throw new Error(error.error || 'Failed to update trash prompt');
  }
  return response.json();
}

export async function restorePrompt(trashName) {
  const response = await fetch(`${API_BASE}/prompts/trash/${encodeURIComponent(trashName)}/restore`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to restore prompt');
  }
  return response.json();
}

export async function clearTrash() {
  const response = await fetch(`${API_BASE}/prompts/trash`, {
    method: 'DELETE',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to clear trash');
  }
  return response.json();
}

// Crawler / Indexer API
export async function getCrawlerSources() {
  const response = await fetch(`${API_BASE}/crawler/sources`);
  if (!response.ok) {
    throw new Error('Failed to get crawler sources');
  }
  return response.json();
}

export async function getCrawlerSourcePages(sourceId) {
  const response = await fetch(`${API_BASE}/crawler/sources/${encodeURIComponent(sourceId)}/pages`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to get source pages');
  }
  return response.json();
}

export async function getCrawlerSourceStats(sourceId) {
  const response = await fetch(`${API_BASE}/crawler/sources/${encodeURIComponent(sourceId)}/stats`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to get source stats');
  }
  return response.json();
}

export async function createCollection(config) {
  const response = await fetch(`${API_BASE}/crawler/create-collection`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to create collection');
  }
  const data = await response.json();
  return { ...data, job_id: data.job_id, statusCode: response.status };
}

export async function getCreateCollectionStatus(jobId) {
  const response = await fetch(`${API_BASE}/crawler/create-collection-status/${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.error || 'Failed to get job status');
  }
  return response.json();
}

export async function crawlSource(sourceId) {
  const response = await fetch(`${API_BASE}/crawler/sources/${encodeURIComponent(sourceId)}/crawl`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || `Failed to start crawl for source ${sourceId}`);
  }
  return response.json();
}

export async function getCrawlStatus(sourceId) {
  const response = await fetch(`${API_BASE}/crawler/sources/${encodeURIComponent(sourceId)}/crawl/status`);
  if (!response.ok) {
    throw new Error(`Failed to get crawl status for source ${sourceId}`);
  }
  return response.json();
}

export async function addCrawlerSource(sourceConfig) {
  const response = await fetch(`${API_BASE}/crawler/sources`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(sourceConfig),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Failed to add source');
  }
  return response.json();
}

export async function getCrawlerSource(sourceId) {
  const response = await fetch(`${API_BASE}/crawler/sources/${encodeURIComponent(sourceId)}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || `Failed to get source ${sourceId}`);
  }
  return response.json();
}

export async function updateCrawlerSource(sourceId, sourceConfig) {
  const response = await fetch(`${API_BASE}/crawler/sources/${encodeURIComponent(sourceId)}`, {
    method: 'PUT',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(sourceConfig),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || `Failed to update source ${sourceId}`);
  }
  return response.json();
}

// --- ClawCode (optional Core Module) ---
const CLAWCODE_BASE = `${API_BASE}/clawcode`;

export async function getClawCodeStatus() {
  const response = await fetch(`${CLAWCODE_BASE}/status`);
  if (!response.ok) {
    throw new Error('Failed to get ClawCode status');
  }
  return response.json();
}

export async function getClawCodeTraces(limit = 40) {
  const response = await fetch(`${CLAWCODE_BASE}/traces?limit=${encodeURIComponent(limit)}`);
  if (!response.ok) {
    throw new Error('Failed to get ClawCode traces');
  }
  return response.json();
}

export async function clearClawCodeTraces() {
  const response = await fetch(`${CLAWCODE_BASE}/traces/clear`, { method: 'POST' });
  if (!response.ok) {
    throw new Error('Failed to clear traces');
  }
  return response.json();
}

export async function getClawCodeJournal(options = {}) {
  const params = new URLSearchParams();
  const { limit, since_id, from, to } = options;
  if (limit != null) params.set('limit', String(limit));
  if (since_id != null) params.set('since_id', String(since_id));
  if (from != null && from !== '') params.set('from', from);
  if (to != null && to !== '') params.set('to', to);
  const response = await fetch(`${CLAWCODE_BASE}/journal?${params}`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.error || 'Failed to load ClawCode journal');
  }
  return data;
}

export async function clearClawCodeJournal() {
  const response = await fetch(`${CLAWCODE_BASE}/journal`, { method: 'DELETE' });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.error || 'Failed to clear ClawCode journal');
  }
  return data;
}

export async function getClawCodeVendorMainSha() {
  const response = await fetch(`${CLAWCODE_BASE}/vendor/main-sha`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    return { ok: false, error: data.error || 'request failed' };
  }
  return data;
}

export async function getClawCodeVendorVersions() {
  const response = await fetch(`${CLAWCODE_BASE}/vendor/versions`);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    return { ok: false, versions: [] };
  }
  return data;
}

export async function syncClawCodeVendor() {
  const response = await fetch(`${CLAWCODE_BASE}/vendor/sync`, { method: 'POST' });
  const data = await response.json().catch(() => ({}));
  return data;
}

export async function rollbackClawCodeVendorPrevious() {
  const response = await fetch(`${CLAWCODE_BASE}/vendor/rollback-previous`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({}),
  });
  const data = await response.json().catch(() => ({}));
  return data;
}

export async function getClawCodeSettings() {
  const response = await fetch(`${CLAWCODE_BASE}/settings`);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.error || 'Failed to get ClawCode settings');
  }
  return response.json();
}

export async function updateClawCodeSettings(settings) {
  const response = await fetch(`${CLAWCODE_BASE}/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(settings),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.ok) {
    throw new Error(data.error || 'Failed to update ClawCode settings');
  }
  return data;
}

