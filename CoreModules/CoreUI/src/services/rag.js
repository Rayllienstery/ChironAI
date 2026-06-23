import { API_BASE, extractApiError } from './http.js';

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

