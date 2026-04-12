// WebUI Frontend Application — API_BASE must match core.contracts.webui_api.WEBUI_URL_PREFIX (Python).
const API_BASE = '/api/webui';

// State
let currentRequest = null;
let currentResponse = null;

// Initialize on DOM load
document.addEventListener('DOMContentLoaded', () => {
    initializeUI();
    loadModels();
    loadLogs();
    setupEventListeners();
});

function initializeUI() {
    // Setup temperature and top-p sliders
    const temperatureSlider = document.getElementById('temperature');
    const temperatureValue = document.getElementById('temperatureValue');
    temperatureSlider.addEventListener('input', (e) => {
        temperatureValue.textContent = (parseFloat(e.target.value) / 10).toFixed(1);
    });
    temperatureValue.textContent = (parseFloat(temperatureSlider.value) / 10).toFixed(1);

    const topPSlider = document.getElementById('topP');
    const topPValue = document.getElementById('topPValue');
    topPSlider.addEventListener('input', (e) => {
        topPValue.textContent = (parseFloat(e.target.value) / 10).toFixed(1);
    });
    topPValue.textContent = (parseFloat(topPSlider.value) / 10).toFixed(1);

    // Setup dev console tabs
    const devTabs = document.querySelectorAll('.dev-tab');
    devTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            switchDevTab(tabName);
        });
    });
}

function setupEventListeners() {
    document.getElementById('sendButton').addEventListener('click', sendQuery);
    document.getElementById('clearButton').addEventListener('click', clearAll);
    document.getElementById('devConsoleToggle').addEventListener('change', toggleDevConsole);
    document.getElementById('refreshLogs').addEventListener('click', loadLogs);
    document.getElementById('logLevel').addEventListener('change', loadLogs);

    // Enter key to send (Ctrl+Enter or Cmd+Enter)
    document.getElementById('queryInput').addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
            sendQuery();
        }
    });
}

async function loadModels() {
    try {
        const response = await fetch(`${API_BASE}/models`);
        const data = await response.json();
        const modelSelect = document.getElementById('modelSelect');
        modelSelect.innerHTML = '';
        data.models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.id;
            option.textContent = model.name;
            modelSelect.appendChild(option);
        });
    } catch (error) {
        console.error('Failed to load models:', error);
    }
}

async function sendQuery() {
    const queryInput = document.getElementById('queryInput');
    const query = queryInput.value.trim();
    
    if (!query) {
        alert('Please enter a query');
        return;
    }

    const sendButton = document.getElementById('sendButton');
    const loadingIndicator = document.getElementById('loadingIndicator');
    const responseContent = document.getElementById('responseContent');

    sendButton.disabled = true;
    loadingIndicator.style.display = 'block';
    responseContent.innerHTML = '';

    // Collect parameters
    const model = document.getElementById('modelSelect').value;
    const temperature = parseFloat(document.getElementById('temperature').value) / 10;
    const topP = parseFloat(document.getElementById('topP').value) / 10;
    const reasoningLevel = document.getElementById('reasoningLevel').value || null;
    const codeOnly = document.getElementById('codeOnly').checked;
    const includeRAGMetadata = document.getElementById('includeRAGMetadata').checked;

    const requestBody = {
        messages: [{ role: 'user', content: query }],
        model: model,
        temperature: temperature > 0 ? temperature : null,
        top_p: topP > 0 ? topP : null,
        reasoning_level: reasoningLevel,
        code_only: codeOnly,
        include_rag_metadata: includeRAGMetadata,
    };

    currentRequest = requestBody;

    try {
        const response = await fetch(`${API_BASE}/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(requestBody),
        });

        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.error || 'Request failed');
        }

        const data = await response.json();
        currentResponse = data;

        // Display response
        if (data.choices && data.choices[0]) {
            const content = data.choices[0].message.content;
            responseContent.innerHTML = marked.parse(content);
            
            // Highlight code blocks
            responseContent.querySelectorAll('pre code').forEach(block => {
                if (typeof Prism !== 'undefined') {
                    Prism.highlightElement(block);
                }
            });
        }

        // Display RAG chunks if available
        if (data.rag_metadata && data.rag_metadata.chunks_info) {
            displayRAGChunks(data.rag_metadata.chunks_info, data.rag_metadata.max_score);
        } else {
            clearRAGChunks();
        }

        // Update dev console
        updateDevConsole(requestBody, data);

    } catch (error) {
        responseContent.innerHTML = `<p style="color: var(--error);">Error: ${error.message}</p>`;
        console.error('Query error:', error);
    } finally {
        sendButton.disabled = false;
        loadingIndicator.style.display = 'none';
    }
}

function displayRAGChunks(chunksInfo, maxScore) {
    const ragChunks = document.getElementById('ragChunks');
    
    if (!chunksInfo || chunksInfo.length === 0) {
        ragChunks.innerHTML = '<p class="empty-state">No RAG chunks found.</p>';
        return;
    }

    let html = `<div style="margin-bottom: 0.5rem; font-size: 0.75rem; color: var(--text-light);">`;
    html += `Found ${chunksInfo.length} chunk(s), max score: ${maxScore.toFixed(4)}</div>`;
    
    chunksInfo.forEach((chunk, index) => {
        html += `
            <div class="chunk-card">
                <div class="chunk-header">
                    <span>Chunk #${chunk.index || index + 1}</span>
                    <div class="chunk-scores">
                        ${chunk.score ? `<span>Score: ${chunk.score}</span>` : ''}
                        ${chunk.rerank_score ? `<span>Rerank: ${chunk.rerank_score}</span>` : ''}
                    </div>
                </div>
                <div class="chunk-meta">
                    ${chunk.url && chunk.url !== 'N/A' ? `<div><strong>URL:</strong> <a href="${chunk.url}" target="_blank">${chunk.url}</a></div>` : ''}
                    ${chunk.doc_type && chunk.doc_type !== 'N/A' ? `<div><strong>Type:</strong> ${chunk.doc_type}</div>` : ''}
                    ${chunk.ios_versions && chunk.ios_versions.length > 0 ? `<div><strong>iOS:</strong> ${chunk.ios_versions.join(', ')}</div>` : ''}
                    ${chunk.swift_versions && chunk.swift_versions.length > 0 ? `<div><strong>Swift:</strong> ${chunk.swift_versions.join(', ')}</div>` : ''}
                </div>
                ${chunk.text_preview ? `<div class="chunk-preview">${escapeHtml(chunk.text_preview)}</div>` : ''}
            </div>
        `;
    });

    ragChunks.innerHTML = html;
}

function clearRAGChunks() {
    document.getElementById('ragChunks').innerHTML = '<p class="empty-state">No RAG chunks yet. Send a query to see retrieved chunks.</p>';
}

async function loadLogs() {
    const logLevel = document.getElementById('logLevel').value;
    const logsContent = document.getElementById('logsContent');
    
    try {
        const params = new URLSearchParams({ limit: '50' });
        if (logLevel) {
            params.append('level', logLevel);
        }
        
        const response = await fetch(`${API_BASE}/logs?${params}`);
        const data = await response.json();
        
        if (!data.logs || data.logs.length === 0) {
            logsContent.innerHTML = '<p class="empty-state">No logs found.</p>';
            return;
        }

        let html = '';
        data.logs.forEach(log => {
            const level = log.level || 'UNKNOWN';
            const timestamp = log.timestamp || log.ts || 'N/A';
            const message = log.message || log.raw || JSON.stringify(log);
            const source = log.source || '';
            const errorType = log.error_type || '';
            
            html += `
                <div class="log-entry ${level.toLowerCase()}">
                    <div><strong>[${level}]</strong> ${timestamp}</div>
                    ${source ? `<div>Source: ${source}</div>` : ''}
                    ${errorType ? `<div>Type: ${errorType}</div>` : ''}
                    <div>${escapeHtml(message)}</div>
                </div>
            `;
        });

        logsContent.innerHTML = html;
    } catch (error) {
        logsContent.innerHTML = `<p style="color: var(--error);">Error loading logs: ${error.message}</p>`;
        console.error('Logs error:', error);
    }
}

function toggleDevConsole() {
    const devConsole = document.getElementById('devConsole');
    const isVisible = devConsole.style.display !== 'none';
    devConsole.style.display = isVisible ? 'none' : 'block';
    
    if (!isVisible && currentRequest) {
        updateDevConsole(currentRequest, currentResponse);
    }
}

function switchDevTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.dev-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelector(`.dev-tab[data-tab="${tabName}"]`).classList.add('active');

    // Update content
    document.querySelectorAll('.dev-pane').forEach(pane => {
        pane.style.display = 'none';
    });

    if (tabName === 'request') {
        document.getElementById('devRequest').style.display = 'block';
        if (currentRequest) {
            document.getElementById('devRequest').textContent = JSON.stringify(currentRequest, null, 2);
        }
    } else if (tabName === 'response') {
        document.getElementById('devResponse').style.display = 'block';
        if (currentResponse) {
            document.getElementById('devResponse').textContent = JSON.stringify(currentResponse, null, 2);
        }
    } else if (tabName === 'systemPrompt') {
        document.getElementById('devSystemPrompt').style.display = 'block';
        if (currentResponse && currentResponse.rag_metadata && currentResponse.rag_metadata.system_prompt_preview) {
            document.getElementById('devSystemPrompt').textContent = currentResponse.rag_metadata.system_prompt_preview;
        } else {
            document.getElementById('devSystemPrompt').textContent = 'No system prompt preview available.';
        }
    } else if (tabName === 'history') {
        document.getElementById('devHistory').style.display = 'block';
        loadDevHistory();
    }
}

async function loadDevHistory() {
    try {
        const response = await fetch(`${API_BASE}/dev-console?limit=20`);
        const data = await response.json();
        
        const historyPane = document.getElementById('devHistory');
        if (!data.requests || data.requests.length === 0) {
            historyPane.textContent = 'No request history available.';
            return;
        }

        let html = '';
        data.requests.reverse().forEach((req, index) => {
            html += `
                <div style="border-bottom: 1px solid var(--border); padding: 0.5rem; margin-bottom: 0.5rem;">
                    <div><strong>#${data.requests.length - index}</strong> ${req.timestamp}</div>
                    <div style="font-size: 0.75rem; color: var(--text-light);">Latency: ${req.latency_ms}ms</div>
                    <details style="margin-top: 0.5rem;">
                        <summary style="cursor: pointer; font-size: 0.75rem;">View Request/Response</summary>
                        <pre style="margin-top: 0.5rem; font-size: 0.7rem; overflow-x: auto;">${escapeHtml(JSON.stringify(req, null, 2))}</pre>
                    </details>
                </div>
            `;
        });

        historyPane.innerHTML = html;
    } catch (error) {
        document.getElementById('devHistory').textContent = `Error loading history: ${error.message}`;
        console.error('History error:', error);
    }
}

function updateDevConsole(request, response) {
    if (document.getElementById('devConsole').style.display === 'none') {
        return;
    }

    const activeTab = document.querySelector('.dev-tab.active');
    if (activeTab) {
        switchDevTab(activeTab.dataset.tab);
    } else {
        switchDevTab('request');
    }
}

function clearAll() {
    document.getElementById('queryInput').value = '';
    document.getElementById('responseContent').innerHTML = '';
    clearRAGChunks();
    currentRequest = null;
    currentResponse = null;
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

