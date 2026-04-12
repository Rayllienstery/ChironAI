import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  getModels,
  getPrompts,
  getTesterSettings,
  updateTesterSettings,
  testerChat,
  testerPromptPreview,
  getRagCollections,
  getLlmProxyBuilds,
} from '../services/api';
import { marked } from 'marked';
import '../styles/components/ModelTester.css';

function ModelTester({ sessionId }) {
  const [models, setModels] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [collections, setCollections] = useState([]);
  const [llmBuilds, setLlmBuilds] = useState([]);
  const [settings, setSettings] = useState({
    model: '',
    prompt_name: '',
    temperature: 0.0,
    top_p: 0.1,
    reasoning_level: '',
    use_rag: true,
    top_k: 4,
    rag_collection: '',
    fetch_web_knowledge: false,
    tester_proxy_mode: 'rag_fusion',
    claw_build_id: '',
  });
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [promptPreview, setPromptPreview] = useState('');
  const [promptPreviewOpen, setPromptPreviewOpen] = useState(false);
  const [promptLoading, setPromptLoading] = useState(false);
  const [ragChunks, setRagChunks] = useState(null);
  const [ragCollapsed, setRagCollapsed] = useState(false);
  const [skillsUsed, setSkillsUsed] = useState(null);
  const responseRef = useRef(null);

  const clawBuilds = useMemo(
    () =>
      (llmBuilds || []).filter((b) => String(b.backend || '').toLowerCase() === 'claw'),
    [llmBuilds]
  );

  useEffect(() => {
    if (sessionId) {
      loadData();
      loadTesterSettings();
    }
  }, [sessionId]);

  useEffect(() => {
    if (!promptPreviewOpen) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setPromptPreviewOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [promptPreviewOpen]);

  const loadData = async () => {
    try {
      const [modelsData, promptsData, collectionsData, buildsData] = await Promise.all([
        getModels(),
        getPrompts(),
        getRagCollections().catch(() => ({ collections: [] })),
        getLlmProxyBuilds().catch(() => ({ builds: [] })),
      ]);
      setModels(modelsData);
      const promptsList = promptsData?.prompts || [];
      setPrompts(promptsList);
      setCollections(collectionsData?.collections || []);
      setLlmBuilds(buildsData?.builds || []);
    } catch (error) {
      console.error('Failed to load data:', error);
    }
  };

  const loadTesterSettings = async () => {
    if (!sessionId) return;
    setSettingsLoading(true);
    try {
      const data = await getTesterSettings(sessionId);
      if (data) {
        setSettings((prev) => ({ ...prev, ...data }));
      }
    } catch (error) {
      console.error('Failed to load tester settings:', error);
    } finally {
      setSettingsLoading(false);
    }
  };

  const handleSettingChange = (field, value) => {
    setSettings((prev) => ({ ...prev, [field]: value }));
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

  const isClawMode = settings.tester_proxy_mode === 'claw';

  const handleSend = async () => {
    if (!query.trim() || !sessionId) return;

    if (isClawMode) {
      if (!(settings.claw_build_id || '').trim()) {
        window.alert('Select a Claw build (configure one under LLM Proxy → Builds if the list is empty).');
        return;
      }
    } else {
      if (settings.use_rag && !(settings.prompt_name || '').trim()) {
        window.alert('Select a prompt template when RAG is enabled.');
        return;
      }
      if (
        settings.use_rag &&
        collections.length > 0 &&
        !(settings.rag_collection || '').trim()
      ) {
        window.alert('Select a RAG collection when RAG is enabled.');
        return;
      }
    }

    setLoading(true);
    setResponse('');
    setStats(null);
    setPromptPreview('');
    setPromptPreviewOpen(false);
    setRagChunks(null);
    setSkillsUsed(null);

    try {
      const result = await testerChat(
        sessionId,
        [{ role: 'user', content: query }],
        {
          model: settings.model || undefined,
          prompt_name: settings.prompt_name || undefined,
          temperature: settings.temperature > 0 ? settings.temperature : undefined,
          top_p: settings.top_p > 0 ? settings.top_p : undefined,
          reasoning_level: settings.reasoning_level || undefined,
          use_rag: settings.use_rag,
          top_k: settings.use_rag ? settings.top_k : undefined,
          collection_name: settings.use_rag && settings.rag_collection ? settings.rag_collection : undefined,
          fetch_web_knowledge: settings.use_rag && settings.fetch_web_knowledge,
          tester_proxy_mode: settings.tester_proxy_mode,
          claw_build_id: isClawMode ? settings.claw_build_id : undefined,
        }
      );

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

      if (result.rag_metadata && Array.isArray(result.rag_metadata.chunks_info)) {
        setRagChunks(result.rag_metadata.chunks_info);
      } else {
        setRagChunks(null);
      }

      const sk = result.skills;
      if (
        sk &&
        typeof sk === 'object' &&
        (Number(sk.loaded_count) > 0 || (Array.isArray(sk.loaded_invocations) && sk.loaded_invocations.length > 0))
      ) {
        setSkillsUsed(sk);
      } else {
        setSkillsUsed(null);
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
    if (isClawMode) return;
    setPromptLoading(true);
    try {
      const result = await testerPromptPreview({
        prompt_name: settings.prompt_name || undefined,
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
      setPromptPreviewOpen(true);
    } catch (error) {
      setPromptPreview(`Error: ${error.message}`);
      setPromptPreviewOpen(true);
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
            <label htmlFor="tester-proxy-mode">Proxy pipeline</label>
            <select
              id="tester-proxy-mode"
              value={settings.tester_proxy_mode === 'claw' ? 'claw' : 'rag_fusion'}
              onChange={(e) => handleSettingChange('tester_proxy_mode', e.target.value)}
            >
              <option value="rag_fusion">RAG Fusion (in-process RAG + Ollama)</option>
              <option value="claw">Claw (ClawCode OpenAI agent)</option>
            </select>
            <div className="form-hint">
              Claw uses the prompt, RAG, and model from the selected build in LLM Proxy Builds.
            </div>
          </div>

          {isClawMode && (
            <div className="form-group">
              <label htmlFor="tester-claw-build">Claw build</label>
              <select
                id="tester-claw-build"
                value={
                  clawBuilds.some((b) => b.id === settings.claw_build_id) ? settings.claw_build_id : ''
                }
                onChange={(e) => handleSettingChange('claw_build_id', e.target.value)}
                disabled={clawBuilds.length === 0}
              >
                {clawBuilds.length === 0 ? (
                  <option value="">— No Claw builds —</option>
                ) : (
                  <>
                    <option value="">Select Claw build…</option>
                    {clawBuilds.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.display_name || b.id}
                      </option>
                    ))}
                  </>
                )}
              </select>
              <div className="form-hint">
                {clawBuilds.length === 0
                  ? 'Add a build with backend “claw” under Proxies → LLM Proxy → Builds.'
                  : 'Must match a build with backend claw.'}
              </div>
            </div>
          )}

          <div className="form-group">
            <label>Model {isClawMode && <span className="form-hint-inline">(RAG Fusion only)</span>}</label>
            <select
              value={models.some((m) => (m.id || m.name) === settings.model) ? settings.model : ''}
              onChange={(e) => handleSettingChange('model', e.target.value)}
              disabled={isClawMode}
            >
              <option value="">Select model…</option>
              {models.map((model) => (
                <option key={model.id || model.name} value={model.id || model.name}>
                  {model.name}
                </option>
              ))}
            </select>
          </div>

          <div className="form-group">
            <label>Prompt Template {isClawMode && <span className="form-hint-inline">(RAG Fusion)</span>}</label>
            <select
              value={
                prompts.some((p) => p.name === settings.prompt_name) ? settings.prompt_name : ''
              }
              onChange={(e) => handleSettingChange('prompt_name', e.target.value)}
              className="prompt-template-select"
              disabled={isClawMode}
            >
              <option value="">Select prompt template…</option>
              {prompts
                .filter((p) => p.name && p.name.toLowerCase() !== 'readme')
                .map((prompt) => (
                  <option key={prompt.id || prompt.name} value={prompt.name}>
                    {prompt.name}
                  </option>
                ))}
            </select>
            {settings.prompt_name && !isClawMode && (
              <div className="prompt-template-info">
                Selected: <strong>{settings.prompt_name}</strong>
              </div>
            )}
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
              disabled={!settings.use_rag || isClawMode}
            />
            <div className="form-hint">Number of RAG chunks to retrieve (1-20), RAG Fusion only</div>
          </div>

          <div className="form-group checkbox-group">
            <label>
              <input
                type="checkbox"
                checked={settings.use_rag}
                onChange={(e) => handleSettingChange('use_rag', e.target.checked)}
                disabled={isClawMode}
              />
              Use RAG
            </label>
          </div>

          {settings.use_rag && !isClawMode && (
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

          {settings.use_rag && !isClawMode && (
            <div className="form-group">
              <label>RAG Collection</label>
              <select
                value={
                  collections.length > 0 &&
                  collections.some((c) => c.name === settings.rag_collection)
                    ? settings.rag_collection
                    : ''
                }
                onChange={(e) => handleSettingChange('rag_collection', e.target.value)}
                disabled={collections.length === 0}
              >
                {collections.length === 0 ? (
                  <option value="">— No collections —</option>
                ) : (
                  <>
                    <option value="">Select RAG collection…</option>
                    {collections.map((col) => (
                      <option key={col.name} value={col.name}>
                        {col.name} ({col.points_count || 0} vectors)
                      </option>
                    ))}
                  </>
                )}
              </select>
              <div className="form-hint">
                {collections.length === 0
                  ? 'No Qdrant collections. Create one in Crawler / RAG then come back.'
                  : 'Select Qdrant collection for RAG retrieval'}
              </div>
            </div>
          )}

          <button type="button" onClick={handleSaveSettings} className="save-button">
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
              }}
              placeholder="Enter your test query..."
              rows="4"
            />
            <div className="chat-input-actions">
              <button
                type="button"
                onClick={handleSend}
                disabled={loading || !query.trim()}
                className="send-button"
              >
                {loading ? 'Sending...' : 'Send'}
              </button>
              <button
                type="button"
                className="preview-button"
                disabled={promptLoading || isClawMode}
                onClick={handlePreviewPrompt}
                title={isClawMode ? 'Prompt preview applies to RAG Fusion only' : undefined}
              >
                {promptLoading ? 'Previewing...' : 'Preview Prompt'}
              </button>
              <div className="tester-stats">
                {loading && <span className="tester-spinner" aria-label="Running model" />}
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
          </div>

          {ragChunks != null && (
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
                          {textToShow && <div className="rag-chunk-text">{textToShow}</div>}
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
            {skillsUsed && (
              <div className="model-tester-skills-used" aria-label="Skills used in this response">
                <h4 className="model-tester-skills-used-title">Skills</h4>
                <p className="model-tester-skills-used-meta">
                  Loaded: {skillsUsed.loaded_count ?? (skillsUsed.loaded_invocations || []).length}
                  {typeof skillsUsed.enabled_count === 'number' ? ` · Enabled in run: ${skillsUsed.enabled_count}` : ''}
                </p>
                {(skillsUsed.loaded_invocations || []).length > 0 && (
                  <ul className="model-tester-skills-used-list">
                    {(skillsUsed.loaded_invocations || []).map((inv) => (
                      <li key={inv}>
                        <code>{inv}</code>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>
        </div>
      </div>

      {promptPreviewOpen && (
        <div
          className="model-tester-modal-overlay"
          role="presentation"
          onClick={() => setPromptPreviewOpen(false)}
        >
          <div
            className="model-tester-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="model-tester-prompt-preview-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="model-tester-modal-header">
              <h2 id="model-tester-prompt-preview-title" className="model-tester-modal-title">
                Prompt preview
              </h2>
              <button
                type="button"
                className="model-tester-modal-close"
                aria-label="Close"
                onClick={() => setPromptPreviewOpen(false)}
              >
                ✕
              </button>
            </div>
            <pre className="model-tester-modal-body">{promptPreview}</pre>
          </div>
        </div>
      )}
    </div>
  );
}

export default ModelTester;
