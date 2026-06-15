import { API_BASE, extractApiError } from './http.js';

export async function getIndexerTesterSources() {
  const response = await fetch(`${API_BASE}/crawler/indexer-tester/sources`);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to get Indexer Tester sources'));
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
    throw new Error(extractApiError(data, 'Failed to get Indexer Tester files'));
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
    throw new Error(extractApiError(data, 'Failed to get Indexer Tester file detail'));
  }
  return response.json();
}

export async function evaluateIndexerWithLlm(
  sourceMd,
  processedMd,
  providerId,
  model,
  pageMeta = null,
  limits = null,
) {
  const body = {
    source_md: sourceMd,
    processed_md: processedMd,
    provider_id: providerId || undefined,
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
    throw new Error(extractApiError(data, 'Evaluate failed'));
  }
  return response.json();
}

export async function startIndexerTesterEvaluateBatch({
  sourceId,
  providerId,
  model,
  count,
  original_max_chars,
  processed_max_chars,
  removed_max_chars,
}) {
  const body = {
    source_id: sourceId,
    provider_id: providerId || undefined,
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
    throw new Error(extractApiError(data, 'Failed to start batch evaluation'));
  }
  return response.json();
}

export async function getIndexerTesterEvaluateBatchStatus(jobId) {
  const response = await fetch(
    `${API_BASE}/crawler/indexer-tester/evaluate-batch/status/${encodeURIComponent(jobId)}`,
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to get batch status'));
  }
  return response.json();
}

export async function detectBatchEvalPatterns(results, providerId, model) {
  const response = await fetch(
    `${API_BASE}/crawler/indexer-tester/evaluate-batch/detect-patterns`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        results: results || [],
        provider_id: providerId || undefined,
        model: model || undefined,
      }),
    },
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to detect patterns'));
  }
  return response.json();
}

// MD Pipelines (config-driven markdown cleanup for RAG)
export async function getMdPipelines() {
  const response = await fetch(`${API_BASE}/crawler/md-pipelines`);
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to list MD pipelines'));
  }
  return response.json();
}

export async function getMdPipeline(name) {
  const response = await fetch(
    `${API_BASE}/crawler/md-pipelines/${encodeURIComponent(name)}`,
  );
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, `Failed to get pipeline ${name}`));
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
    throw new Error(extractApiError(data, 'Failed to save pipeline'));
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
    throw new Error(extractApiError(data, 'Failed to delete pipeline'));
  }
  return response.json();
}

export async function previewMdPipeline(pipelineName, sourceId, filename, pipeline) {
  const response = await fetch(`${API_BASE}/crawler/md-pipelines/preview`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pipeline_name: pipelineName || undefined,
      pipeline: pipeline || undefined,
      source_id: sourceId,
      filename,
    }),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(extractApiError(data, 'Failed to preview pipeline'));
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
    throw new Error(extractApiError(error, 'Failed to get source pages'));
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
    throw new Error(extractApiError(error, 'Failed to create collection'));
  }
  const data = await response.json();
  return { ...data, job_id: data.job_id, statusCode: response.status };
}

export async function getCreateCollectionStatus(jobId) {
  const response = await fetch(`${API_BASE}/crawler/create-collection-status/${encodeURIComponent(jobId)}`);
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(extractApiError(err, 'Failed to get job status'));
  }
  return response.json();
}

export async function cancelCreateCollection(jobId) {
  const response = await fetch(`${API_BASE}/crawler/create-collection-cancel/${encodeURIComponent(jobId)}`, {
    method: 'POST',
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(extractApiError(err, 'Failed to cancel collection creation'));
  }
  return response.json();
}

export async function crawlSource(sourceId) {
  const response = await fetch(`${API_BASE}/crawler/sources/${encodeURIComponent(sourceId)}/crawl`, {
    method: 'POST',
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, `Failed to start crawl for source ${sourceId}`));
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
    throw new Error(extractApiError(error, 'Failed to add source'));
  }
  return response.json();
}

export async function getCrawlerSource(sourceId) {
  const response = await fetch(`${API_BASE}/crawler/sources/${encodeURIComponent(sourceId)}`);
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(extractApiError(error, `Failed to get source ${sourceId}`));
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
    throw new Error(extractApiError(error, `Failed to update source ${sourceId}`));
  }
  return response.json();
}
