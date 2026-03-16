import React, { useState, useEffect, useRef } from 'react';
import { getModels, getPrompts, getTesterSettings, updateTesterSettings, testerChat, testerPromptPreview, getRagCollections } from '../services/api';
import { marked } from 'marked';
import './ModelTester.css';

function ModelTester({ sessionId }) {
  const [models, setModels] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [collections, setCollections] = useState([]);
  const [dataLoaded, setDataLoaded] = useState(false);
  const hasSanitizedRef = useRef(false);
  const [settings, setSettings] = useState({
    model: '',
    prompt_name: '',
    swift_mode: 'default',
    temperature: 0.0,
    top_p: 0.1,
    reasoning_level: '',
    use_rag: true,
    top_k: 4,
    rag_collection: '',
    fetch_web_knowledge: false,
  });
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [promptPreview, setPromptPreview] = useState('');
  const [promptLoading, setPromptLoading] = useState(false);
  const [ragChunks, setRagChunks] = useState(null);
  const [ragCollapsed, setRagCollapsed] = useState(false);
  const responseRef = useRef(null);

  useEffect(() => {
    if (sessionId) {
      loadData();
      loadTesterSettings();
    }
  }, [sessionId]);

  const loadData = async () => {
    setDataLoaded(false);
    try {
      const [modelsData, promptsData, collectionsData] = await Promise.all([
        getModels(),
        getPrompts(),
        getRagCollections().catch(() => ({ collections: [] })),
      ]);
      setModels(modelsData);
      // getPrompts() returns { prompts: [...], swift_modes: [...] }
      const promptsList = promptsData?.prompts || [];
      console.log('Loaded prompts:', promptsList);
      setPrompts(promptsList);
      setCollections(collectionsData?.collections || []);
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setDataLoaded(true);
    }
  };

  const loadTesterSettings = async () => {
    if (!sessionId) return;
    hasSanitizedRef.current = false;
    setSettingsLoading(true);
    try {
      const data = await getTesterSettings(sessionId);
      if (data) {
        setSettings(prev => ({ ...prev, ...data }));
      }
    } catch (error) {
      console.error('Failed to load tester settings:', error);
    } finally {
      setSettingsLoading(false);
    }
  };

  // Reset saved model/collection to default if not present in current ollama/collections lists
  useEffect(() => {
    if (settingsLoading || !dataLoaded || hasSanitizedRef.current) return;
    const modelIds = (models || []).map((m) => m.id || m.name);
    const collectionNames = (collections || []).map((c) => c.name);
    hasSanitizedRef.current = true;
    setSettings((prev) => {
      let next = { ...prev };
      if (prev.model && (modelIds.length === 0 || !modelIds.includes(prev.model))) {
        next.model = '';
      }
      if (prev.rag_collection && (collectionNames.length === 0 || !collectionNames.includes(prev.rag_collection))) {
        next.rag_collection = (collections && collections[0]) ? collections[0].name : '';
      }
      return next;
    });
  }, [settingsLoading, dataLoaded, models, collections]);

  const handleSettingChange = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }));
  };

  const handleSaveSettings = async () => {
    if (!sessionId) return;
    
    try {
      await updateTesterSettings(sessionId, settings);
      alert('Settings saved');
    } catch (error) {
      console.error('Failed to save settings:', error);
      alert('Failed to save settings');
    }
  };

  const handleSend = async () => {
    if (!query.trim() || !sessionId) return;
    
    setLoading(true);
    setResponse('');
    setStats(null);
    setPromptPreview('');
    setRagChunks(null);
    
    try {
      const result = await testerChat(sessionId, [
        { role: 'user', content: query }
      ], {
        model: settings.model || undefined,
        prompt_name: settings.prompt_name || undefined,
        swift_mode: settings.swift_mode !== 'default' ? settings.swift_mode : undefined,
        temperature: settings.temperature > 0 ? settings.temperature : undefined,
        top_p: settings.top_p > 0 ? settings.top_p : undefined,
        reasoning_level: settings.reasoning_level || undefined,
        use_rag: settings.use_rag,
        top_k: settings.use_rag ? settings.top_k : undefined,
        collection_name: settings.use_rag && settings.rag_collection ? settings.rag_collection : undefined,
        fetch_web_knowledge: settings.use_rag && settings.fetch_web_knowledge,
      });
      
      if (result.choices && result.choices[0]) {
        const content = result.choices[0].message.content;
        setResponse(marked.parse(content));
      }

      if (result.usage || typeof result.latency_ms === 'number') {
        setStats({
          latencyMs: typeof result.latency_ms === 'number' ? result.latency_ms : null,
          promptTokens: result.usage?.prompt_tokens ?? null,
          completionTokens: result.usage?.completion_tokens ?? null,
          totalTokens: result.usage?.total_tokens ?? null,
          contextChars: result.rag_metadata?.context_chars ?? null,
        });
      }

      if (settings.use_rag && result.rag_metadata) {
        setRagChunks(result.rag_metadata.chunks_info || []);
      } else {
        setRagChunks(null);
      }
    } catch (error) {
      setResponse(`Error: ${error.message}`);
    } finally {
      setLoading(false);
      if (responseRef.current) {
        responseRef.current.scrollTop = responseRef.current.scrollHeight;
      }
    }
  };

  const handlePreviewPrompt = async () => {
    setPromptLoading(true);
    try {
      const result = await testerPromptPreview({
        prompt_name: settings.prompt_name || undefined,
        swift_mode: settings.swift_mode,
        user_message: query || '',
        use_rag: settings.use_rag,
      });
      let formattedPreview = '';
      if (result.system_message_full || result.preview_messages) {
        const systemText = result.system_message_full || result.system_prompt || '';
        const userMsg =
          (Array.isArray(result.preview_messages)
            ? result.preview_messages.find((m) => m.role === 'user')?.content
            : null) || (query || '<<your next chat message will be inserted here>>');
        formattedPreview = [
          'SYSTEM MESSAGE (sent as role=system):',
          '',
          systemText,
          '',
          '---',
          '',
          'USER MESSAGE (sent as role=user after the system message):',
          '',
          userMsg,
        ].join('\n');
      } else {
        formattedPreview = result.system_prompt || '';
      }
      setPromptPreview(formattedPreview);
    } catch (error) {
      setPromptPreview(`Error: ${error.message}`);
    } finally {
      setPromptLoading(false);
    }
  };

  const cleanChunkText = (text) => {
    if (!text) return '';

    return text
      .split('\n')
      .filter((line) => {
        const trimmed = line.trim();
        if (!trimmed) return false;

        const lower = trimmed.toLowerCase();
        if (trimmed.startsWith('<!--')) return false;
        if (lower.startsWith('meta:')) return false;
        if (lower.startsWith('url:')) return false;

        return true;
      })
      .join('\n')
      .trim();
  };

  if (!sessionId) {
    return <div className="loading">No session available</div>;
  }

  if (settingsLoading) {
    return <div className="loading">Loading tester settings...</div>;
  }

  return (
    <div className="model-tester">
      <div className="tester-layout">
        <div className="tester-settings-panel">
          <h3>Test Settings</h3>
          
          <div className="form-group">
            <label>Model</label>
            <select
              value={settings.model}
              onChange={(e) => handleSettingChange('model', e.target.value)}
            >
              <option value="">Default (rag-ollama)</option>
              {models.map((model) => (
                <option key={model.id || model.name} value={model.id || model.name}>
                  {model.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Prompt Template</label>
            <select
              value={settings.prompt_name}
              onChange={(e) => handleSettingChange('prompt_name', e.target.value)}
              className="prompt-template-select"
            >
              <option value="">Default (system_rag_v1)</option>
              {prompts
                .filter((p) => p.name && p.name.toLowerCase() !== 'readme')
                .map((prompt) => (
                  <option key={prompt.id || prompt.name} value={prompt.name}>
                    {prompt.name}
                  </option>
                ))}
            </select>
            {settings.prompt_name && (
              <div className="prompt-template-info">
                Selected: <strong>{settings.prompt_name}</strong>
              </div>
            )}
          </div>

          <div className="form-group">
            <label>Swift Mode</label>
            <select
              value={settings.swift_mode}
              onChange={(e) => handleSettingChange('swift_mode', e.target.value)}
            >
              <option value="default">Default</option>
              <option value="swift5">Swift 5</option>
              <option value="swift6">Swift 6</option>
            </select>
          </div>

          <div className="form-group">
            <label>
              Temperature: {settings.temperature.toFixed(1)}
            </label>
            <input
              type="range"
              min="0"
              max="20"
              step="0.1"
              value={settings.temperature * 10}
              onChange={(e) => handleSettingChange('temperature', parseFloat(e.target.value) / 10)}
            />
          </div>

          <div className="form-group">
            <label>
              Top-p: {settings.top_p.toFixed(1)}
            </label>
            <input
              type="range"
              min="0"
              max="10"
              step="0.1"
              value={settings.top_p * 10}
              onChange={(e) => handleSettingChange('top_p', parseFloat(e.target.value) / 10)}
            />
          </div>

          <div className="form-group">
            <label>Reasoning Level</label>
            <select
              value={settings.reasoning_level}
              onChange={(e) => handleSettingChange('reasoning_level', e.target.value)}
            >
              <option value="">Auto</option>
              <option value="low">Low</option>
              <option value="medium">Medium</option>
              <option value="high">High</option>
            </select>
          </div>

          <div className="form-group">
            <label>
              Top K: {settings.top_k}
            </label>
            <input
              type="range"
              min="1"
              max="20"
              step="1"
              value={settings.top_k}
              onChange={(e) => handleSettingChange('top_k', parseInt(e.target.value, 10))}
              disabled={!settings.use_rag}
            />
            <div className="form-hint">
              Number of RAG chunks to retrieve (1-20)
            </div>
          </div>

          <div className="form-group checkbox-group">
            <label>
              <input
                type="checkbox"
                checked={settings.use_rag}
                onChange={(e) => handleSettingChange('use_rag', e.target.checked)}
              />
              Use RAG
            </label>
          </div>

          {settings.use_rag && (
            <div className="form-group checkbox-group">
              <label>
                <input
                  type="checkbox"
                  checked={settings.fetch_web_knowledge}
                  onChange={(e) => handleSettingChange('fetch_web_knowledge', e.target.checked)}
                />
                Fetch Web knowledge
              </label>
              <div className="form-hint">
                Fetch framework docs from the web (e.g. Alamofire, TCA) and merge with RAG context
              </div>
            </div>
          )}

          {settings.use_rag && (
            <div className="form-group">
              <label>RAG Collection</label>
              <select
                value={collections.length === 0 ? '' : (settings.rag_collection || (collections[0]?.name ?? ''))}
                onChange={(e) => handleSettingChange('rag_collection', e.target.value)}
                disabled={collections.length === 0}
              >
                {collections.length === 0 ? (
                  <option value="">— No collections —</option>
                ) : (
                  collections.map((col) => (
                    <option key={col.name} value={col.name}>
                      {col.name} ({col.points_count || 0} vectors)
                    </option>
                  ))
                )}
              </select>
              <div className="form-hint">
                {collections.length === 0
                  ? 'No Qdrant collections. Create one in Crawler / RAG then come back.'
                  : 'Select Qdrant collection for RAG retrieval'}
              </div>
            </div>
          )}

          <button onClick={handleSaveSettings} className="save-button">
            Save Settings
          </button>
        </div>

        <div className="tester-chat-panel">
          <div className="chat-input-section">
            <h3>Query</h3>
            <textarea
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setPromptPreview('');
              }}
              placeholder="Enter your test query..."
              rows="4"
            />
            <div className="chat-input-actions">
              <button
                onClick={handleSend}
                disabled={loading || !query.trim()}
                className="send-button"
              >
                {loading ? 'Sending...' : 'Send'}
              </button>
              <button
                type="button"
                className="preview-button"
                disabled={promptLoading}
                onClick={handlePreviewPrompt}
              >
                {promptLoading ? 'Previewing...' : 'Preview Prompt'}
              </button>
              <div className="tester-stats">
                {loading && (
                  <span className="tester-spinner" aria-label="Running model" />
                )}
                {!loading && stats && (
                  <span className="tester-stats-text">
                    {stats.latencyMs != null && (
                      <span className="tester-stat-pill">
                        ⏱ {(stats.latencyMs / 1000).toFixed(2)} s
                      </span>
                    )}
                    {stats.promptTokens != null && stats.completionTokens != null && (
                      <span className="tester-stat-pill">
                        🔢 {stats.promptTokens} in / {stats.completionTokens} out
                      </span>
                    )}
                    {stats.contextChars != null && (
                      <span className="tester-stat-pill">
                        📚 {stats.contextChars} context chars
                      </span>
                    )}
                  </span>
                )}
              </div>
            </div>
            {promptPreview && (
              <div className="prompt-preview">
                <div className="prompt-preview-header">
                  <span>System Prompt Preview</span>
                  <button
                    type="button"
                    className="prompt-preview-close"
                    aria-label="Close prompt preview"
                    onClick={() => setPromptPreview('')}
                  >
                    ✕
                  </button>
                </div>
                <pre>{promptPreview}</pre>
              </div>
            )}
          </div>

          {settings.use_rag && ragChunks && (
            <div className="rag-chunks-section">
              <div className="rag-chunks-header">
                <h3>RAG Chunks</h3>
                <button
                  type="button"
                  className="rag-chunks-toggle"
                  onClick={() => setRagCollapsed((prev) => !prev)}
                  aria-expanded={!ragCollapsed}
                  aria-label={ragCollapsed ? 'Expand RAG chunks' : 'Collapse RAG chunks'}
                >
                  {ragCollapsed ? '▾' : '▴'}
                </button>
              </div>
              {!ragCollapsed && (
                <div className="rag-chunks-list">
                  {ragChunks.length === 0 ? (
                    <div className="rag-chunk-empty">No relevant fragments from RAG.</div>
                  ) : (
                    ragChunks.map((chunk, index) => {
                      const textToShow = cleanChunkText(chunk.text_preview || chunk.text);

                      return (
                        <div key={index} className="rag-chunk-item">
                          <div className="rag-chunk-header">
                            <span className="rag-chunk-index">#{chunk.index ?? index + 1}</span>
                            {chunk.score != null && (
                              <span className="rag-chunk-score">
                                score: {Number(chunk.score).toFixed(3)}
                              </span>
                            )}
                            {chunk.rerank_score != null && (
                              <span className="rag-chunk-rerank">
                                rerank: {Number(chunk.rerank_score).toFixed(3)}
                              </span>
                            )}
                          </div>
                          {chunk.url && chunk.url !== 'N/A' && (
                            <div className="rag-chunk-url">{chunk.url}</div>
                          )}
                          {textToShow && (
                            <div className="rag-chunk-text">
                              {textToShow}
                            </div>
                          )}
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          )}

          <div className="chat-response-section">
            <h3>Response</h3>
            <div ref={responseRef} className="response-content">
              {loading ? (
                <div className="loading">Generating response...</div>
              ) : response ? (
                <div dangerouslySetInnerHTML={{ __html: response }} />
              ) : (
                <div className="empty-state">No response yet</div>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export default ModelTester;

