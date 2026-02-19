import React, { useState, useEffect, useRef } from 'react';
import { getModels, getPrompts, getTesterSettings, updateTesterSettings, testerChat, testerPromptPreview } from '../services/api';
import { marked } from 'marked';
import './ModelTester.css';

function ModelTester({ sessionId }) {
  const [models, setModels] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [settings, setSettings] = useState({
    prompt_name: '',
    swift_mode: 'default',
    temperature: 0.0,
    top_p: 0.1,
    reasoning_level: '',
    use_rag: true,
  });
  const [query, setQuery] = useState('');
  const [response, setResponse] = useState('');
  const [loading, setLoading] = useState(false);
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [stats, setStats] = useState(null);
  const [promptPreview, setPromptPreview] = useState('');
  const [promptLoading, setPromptLoading] = useState(false);
  const responseRef = useRef(null);

  useEffect(() => {
    if (sessionId) {
      loadData();
      loadTesterSettings();
    }
  }, [sessionId]);

  const loadData = async () => {
    try {
      const [modelsData, promptsData] = await Promise.all([
        getModels(),
        getPrompts(),
      ]);
      setModels(modelsData);
      setPrompts(promptsData.prompts || []);
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
        setSettings(prev => ({ ...prev, ...data }));
      }
    } catch (error) {
      console.error('Failed to load tester settings:', error);
    } finally {
      setSettingsLoading(false);
    }
  };

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
    
    try {
      const result = await testerChat(sessionId, [
        { role: 'user', content: query }
      ], {
        prompt_name: settings.prompt_name || undefined,
        swift_mode: settings.swift_mode !== 'default' ? settings.swift_mode : undefined,
        temperature: settings.temperature > 0 ? settings.temperature : undefined,
        top_p: settings.top_p > 0 ? settings.top_p : undefined,
        reasoning_level: settings.reasoning_level || undefined,
        use_rag: settings.use_rag,
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
        });
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
      });
      setPromptPreview(result.system_prompt || '');
    } catch (error) {
      setPromptPreview(`Error: ${error.message}`);
    } finally {
      setPromptLoading(false);
    }
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
            <label>Prompt Template</label>
            <select
              value={settings.prompt_name}
              onChange={(e) => handleSettingChange('prompt_name', e.target.value)}
            >
              <option value="">Default</option>
              {prompts.map((prompt) => (
                <option key={prompt.id} value={prompt.name}>
                  {prompt.name}
                </option>
              ))}
            </select>
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
                    {stats.totalTokens != null && (
                      <span className="tester-stat-pill">
                        🔢 {stats.totalTokens} tokens
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

