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

export async function getModels() {
  const response = await fetch(`${API_BASE}/models`);
  if (!response.ok) {
    throw new Error('Failed to get models');
  }
  const data = await response.json();
  return data.models;
}

export async function getPrompts() {
  const response = await fetch(`${API_BASE}/prompts`);
  if (!response.ok) {
    throw new Error('Failed to get prompts');
  }
  const data = await response.json();
  return data.prompts;
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
  if (!response.ok) {
    throw new Error('Failed to get RAG collections');
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

