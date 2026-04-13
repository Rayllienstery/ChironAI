import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react';
import {
  getModels,
  getPrompts,
  getTesterSettings,
  updateTesterSettings,
  testerChat,
  testerPromptPreview,
  getRagCollections,
  getLlmProxyBuilds,
  fetchClawCodeSkillMarkdown,
} from '../services/api';
import { CHIRONAI_RAG_TRACE_EVENT, CHIRONAI_RAG_TRACE_STORAGE_KEY } from './RagTraceTimeline';
import { renderTesterMarkdown } from '../utils/modelTesterMarkdown';
import { buildTesterRunLogCards } from '../utils/testerRunLog';
import '../styles/components/ModelTester.css';

function ModelTester({ sessionId }) {
  const [models, setModels] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [collections, setCollections] = useState([]);
  /** From GET /rag/collections (effective default_rag_top_k); used for Claw override placeholder when build has no rag_top_k. */
  const [ragDefaultTopK, setRagDefaultTopK] = useState(null);
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
    claw_override_rag_collection: '',
    claw_override_rag_top_k: '',
    claw_override_max_agent_steps: '',
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
  const [lastRunResult, setLastRunResult] = useState(null);
  const [runLogError, setRunLogError] = useState(null);
  const [runLogCollapsed, setRunLogCollapsed] = useState(false);
  const [debugTraceCollapsed, setDebugTraceCollapsed] = useState(true);
  const [skillModalOpen, setSkillModalOpen] = useState(false);
  const [skillModalTitle, setSkillModalTitle] = useState('');
  const [skillModalBody, setSkillModalBody] = useState('');
  const [skillModalLoading, setSkillModalLoading] = useState(false);
  const [skillModalError, setSkillModalError] = useState(null);
  const [responseModalOpen, setResponseModalOpen] = useState(false);
  const responseRef = useRef(null);

  const clawBuilds = useMemo(
    () =>
      (llmBuilds || []).filter((b) => String(b.backend || '').toLowerCase() === 'claw'),
    [llmBuilds]
  );

  const selectedClawBuild = useMemo(() => {
    const id = (settings.claw_build_id || '').trim();
    if (!id) return null;
    return clawBuilds.find((b) => b.id === id) || null;
  }, [clawBuilds, settings.claw_build_id]);

  const clawOverridePlaceholders = useMemo(() => {
    const b = selectedClawBuild;
    const coll =
      b == null
        ? 'select a Claw build'
        : (b.rag_collection || '').trim() || '(app: clawcode_rag_collection)';
    let topKLabel;
    if (b == null) {
      topKLabel = '—';
    } else if (b.rag_top_k != null && String(b.rag_top_k).trim() !== '') {
      topKLabel = String(b.rag_top_k);
    } else if (ragDefaultTopK != null) {
      topKLabel = String(ragDefaultTopK);
    } else {
      topKLabel = '—';
    }
    const steps =
      b == null
        ? '—'
        : b.max_agent_steps != null && String(b.max_agent_steps).trim() !== ''
          ? String(b.max_agent_steps)
          : 'ClawCode server default';
    return {
      collection: `Default: ${coll}`,
      topK: `Default: ${topKLabel}`,
      maxSteps: `Default: ${steps}`,
    };
  }, [selectedClawBuild, ragDefaultTopK]);

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

  useEffect(() => {
    if (!responseModalOpen) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setResponseModalOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [responseModalOpen]);

  useEffect(() => {
    if (!skillModalOpen) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setSkillModalOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [skillModalOpen]);

  const openSkillMarkdownModal = useCallback(async (invocation) => {
    const inv = String(invocation || '').trim();
    if (!inv) return;
    setSkillModalOpen(true);
    setSkillModalTitle(inv);
    setSkillModalBody('');
    setSkillModalError(null);
    setSkillModalLoading(true);
    try {
      const data = await fetchClawCodeSkillMarkdown({ invocation: inv });
      setSkillModalTitle(data.invocation_name || inv);
      let text = data.content != null ? String(data.content) : '';
      if (data.truncated) text += '\n\n…[truncated]';
      setSkillModalBody(text);
    } catch (e) {
      setSkillModalError(e.message || 'Failed to load skill');
    } finally {
      setSkillModalLoading(false);
    }
  }, []);

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
      const dtk = collectionsData?.default_rag_top_k;
      if (dtk != null && String(dtk).trim() !== '') {
        const n = parseInt(String(dtk), 10);
        if (!Number.isNaN(n)) setRagDefaultTopK(n);
      }
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

  const clawRunLogContext = useMemo(() => {
    if (!isClawMode || !selectedClawBuild) return null;
    const b = selectedClawBuild;
    return {
      buildId: b.id != null ? String(b.id) : '',
      buildLabel: (b.name && String(b.name).trim()) || (b.id != null ? String(b.id) : 'Claw build'),
      ollamaModel: b.ollama_model != null ? String(b.ollama_model) : '',
      ragEnabled: Boolean(b.rag_enabled),
      skillsEnabled: Boolean(b.skills_enabled),
      maxAgentSteps:
        b.max_agent_steps != null && String(b.max_agent_steps).trim() !== '' ? b.max_agent_steps : null,
    };
  }, [isClawMode, selectedClawBuild]);

  const runLogModel = useMemo(
    () =>
      buildTesterRunLogCards({
        result: lastRunResult,
        isClawMode,
        errorMessage: runLogError,
        clawBuildContext: clawRunLogContext,
      }),
    [lastRunResult, isClawMode, runLogError, clawRunLogContext]
  );

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
    setResponseModalOpen(false);
    setStats(null);
    setPromptPreview('');
    setPromptPreviewOpen(false);
    setRagChunks(null);
    setLastRunResult(null);
    setRunLogError(null);

    try {
      const clawTopKRaw = String(settings.claw_override_rag_top_k || '').trim();
      const clawTopKParsed = clawTopKRaw ? parseInt(clawTopKRaw, 10) : NaN;
      const clawStepsRaw = String(settings.claw_override_max_agent_steps || '').trim();
      const clawStepsParsed = clawStepsRaw ? parseInt(clawStepsRaw, 10) : NaN;
      const clawOpts =
        isClawMode
          ? {
              claw_build_id: settings.claw_build_id,
              ...(settings.claw_override_rag_collection.trim()
                ? { claw_override_rag_collection: settings.claw_override_rag_collection.trim() }
                : {}),
              ...(!Number.isNaN(clawTopKParsed) ? { claw_override_rag_top_k: clawTopKParsed } : {}),
              ...(!Number.isNaN(clawStepsParsed) ? { claw_override_max_agent_steps: clawStepsParsed } : {}),
            }
          : {};

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
          ...clawOpts,
        }
      );

      if (result.choices && result.choices[0]) {
        const content = result.choices[0].message.content;
        setResponse(renderTesterMarkdown(content));
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

      if (result.rag_metadata && Array.isArray(result.rag_metadata.rag_trace)) {
        const tr = result.rag_metadata.rag_trace;
        if (tr.length > 0) {
          const lat = typeof result.latency_ms === 'number' ? result.latency_ms : null;
          try {
            sessionStorage.setItem(
              CHIRONAI_RAG_TRACE_STORAGE_KEY,
              JSON.stringify({ trace: tr, latencyMs: lat, updatedAt: Date.now() })
            );
          } catch (_) {
            /* ignore */
          }
          window.dispatchEvent(
            new CustomEvent(CHIRONAI_RAG_TRACE_EVENT, { detail: { trace: tr, latencyMs: lat } })
          );
        }
      }

      setLastRunResult(result);
      setRunLogError(null);
      setRunLogCollapsed(false);
    } catch (error) {
      setLastRunResult(null);
      setRunLogError(error.message || String(error));
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

  const copyDebugTraceRows = () => {
    const rows = runLogModel.debugRows || [];
    if (rows.length === 0) return;
    const text = rows.map((r) => `${r.label}: ${r.value}`).join('\n');
    try {
      void navigator.clipboard?.writeText(text);
    } catch (_) {
      /* ignore */
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
              {isClawMode
                ? 'Uses the selected LLM Proxy build (backend claw): model, RAG tool, skills, and build defaults are forwarded to ClawCode. Sampling sliders below override request temperature / top_p.'
                : 'Single-shot chat with optional in-process RAG: choose Ollama model, prompt template, and Qdrant collection here.'}
            </div>
          </div>

          {!isClawMode && (
            <div className="tester-mode-section tester-mode-section--fusion">
              <h4 className="tester-mode-section-title">RAG Fusion</h4>

              <div className="form-group">
                <label htmlFor="tester-fusion-model">Model</label>
                <select
                  id="tester-fusion-model"
                  value={models.some((m) => (m.id || m.name) === settings.model) ? settings.model : ''}
                  onChange={(e) => handleSettingChange('model', e.target.value)}
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
                <label htmlFor="tester-fusion-prompt">Prompt template</label>
                <select
                  id="tester-fusion-prompt"
                  value={
                    prompts.some((p) => p.name === settings.prompt_name) ? settings.prompt_name : ''
                  }
                  onChange={(e) => handleSettingChange('prompt_name', e.target.value)}
                  className="prompt-template-select"
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
                {settings.prompt_name && (
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
                <label htmlFor="tester-fusion-reasoning">Reasoning level</label>
                <select
                  id="tester-fusion-reasoning"
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

              {settings.use_rag && (
                <>
                  <div className="form-group">
                    <label>
                      Top K (retrieval): {settings.top_k}
                    </label>
                    <input
                      type="range"
                      min="1"
                      max="20"
                      step="1"
                      value={settings.top_k}
                      onChange={(e) => handleSettingChange('top_k', parseInt(e.target.value, 10))}
                    />
                    <div className="form-hint">Number of RAG chunks to retrieve (1–20) for this tester path.</div>
                  </div>

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
                      Fetch framework docs from the web and merge with RAG context when applicable.
                    </div>
                  </div>

                  <div className="form-group">
                    <label htmlFor="tester-fusion-collection">RAG collection</label>
                    <select
                      id="tester-fusion-collection"
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
                        : 'Qdrant collection for this Fusion request.'}
                    </div>
                  </div>
                </>
              )}
            </div>
          )}

          {isClawMode && (
            <div className="tester-mode-section tester-mode-section--claw">
              <h4 className="tester-mode-section-title">Claw (ClawCode agent)</h4>

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
                    ? 'Add a build with backend “claw” under LLM Proxy → Builds.'
                    : 'Build defines Ollama tag, RAG tool on/off, skills, max agent steps, and default RAG fields.'}
                </div>
              </div>

              {selectedClawBuild && (
                <div className="tester-claw-build-summary" aria-label="Selected build summary">
                  <div className="tester-claw-build-summary-title">Build profile</div>
                  <dl className="tester-claw-build-summary-dl">
                    <dt>Ollama model</dt>
                    <dd><code>{selectedClawBuild.ollama_model || '—'}</code></dd>
                    <dt>RAG tool</dt>
                    <dd>{selectedClawBuild.rag_enabled !== false ? 'On' : 'Off'}</dd>
                    <dt>Skills tool</dt>
                    <dd>{selectedClawBuild.skills_enabled !== false ? 'On' : 'Off'}</dd>
                    <dt>Max agent steps</dt>
                    <dd>{selectedClawBuild.max_agent_steps ?? '—'}</dd>
                    <dt>Build RAG collection</dt>
                    <dd>{(selectedClawBuild.rag_collection || '').trim() || '—'}</dd>
                    <dt>Build rag_top_k</dt>
                    <dd>{selectedClawBuild.rag_top_k != null ? selectedClawBuild.rag_top_k : '—'}</dd>
                    <dt>Build temperature / top_p</dt>
                    <dd>
                      {selectedClawBuild.temperature != null ? selectedClawBuild.temperature : '—'} /{' '}
                      {selectedClawBuild.top_p != null ? selectedClawBuild.top_p : '—'}
                    </dd>
                    <dt>Reasoning (build)</dt>
                    <dd>{(selectedClawBuild.reasoning_level || '').trim() || '—'}</dd>
                    <dt>Think mode</dt>
                    <dd>{selectedClawBuild.chat_think ? 'On' : 'Off'}</dd>
                  </dl>
                  <p className="form-hint" style={{ marginTop: 8 }}>
                    If the build leaves RAG collection empty, ClawCode falls back to app setting{' '}
                    <code>clawcode_rag_collection</code>. Final chunk count still follows{' '}
                    <code>retrieval.yaml</code> unless you set rag_top_k on the build or an override below.
                  </p>
                </div>
              )}

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
                <div className="form-hint">Sent on this request; build default applies only if omitted.</div>
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

              <div className="tester-claw-overrides">
                <div className="tester-claw-overrides-title">Tester overrides (optional)</div>
                <p className="form-hint">
                  Leave blank to use the default shown in each placeholder (build → server).
                </p>
                <div className="form-group">
                  <label htmlFor="tester-claw-ov-collection">Override RAG collection</label>
                  <input
                    id="tester-claw-ov-collection"
                    type="text"
                    className="tester-claw-override-input"
                    placeholder={clawOverridePlaceholders.collection}
                    title={clawOverridePlaceholders.collection}
                    value={settings.claw_override_rag_collection}
                    onChange={(e) => handleSettingChange('claw_override_rag_collection', e.target.value)}
                    autoComplete="off"
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="tester-claw-ov-topk">Override rag_query default top_k (1–256)</label>
                  <input
                    id="tester-claw-ov-topk"
                    type="number"
                    min={1}
                    max={256}
                    className="tester-claw-override-input"
                    placeholder={clawOverridePlaceholders.topK}
                    title={clawOverridePlaceholders.topK}
                    value={settings.claw_override_rag_top_k}
                    onChange={(e) => handleSettingChange('claw_override_rag_top_k', e.target.value)}
                  />
                </div>
                <div className="form-group">
                  <label htmlFor="tester-claw-ov-steps">Override max agent steps (1–256)</label>
                  <input
                    id="tester-claw-ov-steps"
                    type="number"
                    min={1}
                    max={256}
                    className="tester-claw-override-input"
                    placeholder={clawOverridePlaceholders.maxSteps}
                    title={clawOverridePlaceholders.maxSteps}
                    value={settings.claw_override_max_agent_steps}
                    onChange={(e) => handleSettingChange('claw_override_max_agent_steps', e.target.value)}
                  />
                </div>
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

          <div className="rag-chunks-section tester-run-log-section">
            <div className="rag-chunks-header">
              <h3>Run log</h3>
              <button
                type="button"
                className="rag-chunks-toggle"
                onClick={() => setRunLogCollapsed((prev) => !prev)}
                aria-expanded={!runLogCollapsed}
                aria-label={runLogCollapsed ? 'Expand run log' : 'Collapse run log'}
              >
                {runLogCollapsed ? '▾' : '▴'}
              </button>
            </div>
            {!runLogCollapsed && (
              <div className="rag-chunks-list">
                {loading && (
                  <div className="rag-chunk-empty" aria-live="polite">
                    Running…
                  </div>
                )}
                {!loading && !lastRunResult && !runLogError && (
                  <div className="rag-chunk-empty">Send a query to populate this log.</div>
                )}
                {!loading &&
                  runLogModel.cards.map((card) => (
                    <div
                      key={card.key}
                      className={`rag-chunk-item${card.skillClickable ? ' rag-chunk-item--clickable' : ''}`}
                      role={card.skillClickable ? 'button' : undefined}
                      tabIndex={card.skillClickable ? 0 : undefined}
                      onClick={() => {
                        if (card.skillClickable && card.invocation) {
                          openSkillMarkdownModal(card.invocation);
                        }
                      }}
                      onKeyDown={(e) => {
                        if (!card.skillClickable || !card.invocation) return;
                        if (e.key === 'Enter' || e.key === ' ') {
                          e.preventDefault();
                          openSkillMarkdownModal(card.invocation);
                        }
                      }}
                    >
                      <div className="rag-chunk-header">
                        <span className="rag-chunk-index">{card.indexLabel}</span>
                        {card.title ? (
                          <span className="rag-chunk-step-title">{card.title}</span>
                        ) : null}
                        {card.badges.map((b) => (
                          <span
                            key={b.key}
                            className={b.variant === 'rerank' ? 'rag-chunk-rerank' : 'rag-chunk-score'}
                          >
                            {b.text}
                          </span>
                        ))}
                      </div>
                      {card.body ? <div className="rag-chunk-text">{card.body}</div> : null}
                    </div>
                  ))}
                {runLogModel.debugRows && runLogModel.debugRows.length > 0 ? (
                  <div className="tester-debug-trace-wrap">
                    <div className="tester-debug-trace-header">
                      <button
                        type="button"
                        className="tester-debug-trace-toggle"
                        onClick={() => setDebugTraceCollapsed((p) => !p)}
                        aria-expanded={!debugTraceCollapsed}
                      >
                        {debugTraceCollapsed ? '▾' : '▴'} Debug · Trace IDs
                      </button>
                      <button type="button" className="tester-debug-trace-copy" onClick={copyDebugTraceRows}>
                        Copy all
                      </button>
                    </div>
                    {!debugTraceCollapsed ? (
                      <ul className="tester-debug-trace-list">
                        {runLogModel.debugRows.map((row) => (
                          <li key={`${row.label}-${row.value}`}>
                            <span className="tester-debug-trace-label">{row.label}</span>{' '}
                            <code className="tester-debug-trace-value">{row.value}</code>
                          </li>
                        ))}
                      </ul>
                    ) : null}
                  </div>
                ) : null}
              </div>
            )}
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
            <div
              ref={responseRef}
              className={`response-content${response && !loading ? ' response-content--clickable' : ''}`}
              onClick={() => {
                if (response && !loading) setResponseModalOpen(true);
              }}
              role={response && !loading ? 'button' : undefined}
              tabIndex={response && !loading ? 0 : undefined}
              aria-label={response && !loading ? 'View full response' : undefined}
            >
              {loading ? (
                <div className="loading">Generating response...</div>
              ) : response ? (
                <div className="model-tester-response-markdown-shell model-tester-response-markdown-shell--embed response-content__inner">
                  <div
                    className="markdown-prose markdown-prose--preview"
                    dangerouslySetInnerHTML={{ __html: response }}
                  />
                </div>
              ) : (
                <div className="empty-state">No response yet</div>
              )}
            </div>
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

      {responseModalOpen && response && (
        <div
          className="model-tester-modal-overlay"
          role="presentation"
          onClick={() => setResponseModalOpen(false)}
        >
          <div
            className="model-tester-modal model-tester-modal--response"
            role="dialog"
            aria-modal="true"
            aria-labelledby="model-tester-response-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="model-tester-modal-header">
              <h2 id="model-tester-response-modal-title" className="model-tester-modal-title">
                Response
              </h2>
              <button
                type="button"
                className="model-tester-modal-close"
                aria-label="Close"
                onClick={() => setResponseModalOpen(false)}
              >
                ✕
              </button>
            </div>
            <div className="model-tester-modal-body model-tester-response-markdown-shell model-tester-response-markdown-shell--modal">
              <div
                className="markdown-prose markdown-prose--preview"
                dangerouslySetInnerHTML={{ __html: response }}
              />
            </div>
          </div>
        </div>
      )}

      {skillModalOpen && (
        <div
          className="model-tester-modal-overlay"
          role="presentation"
          onClick={() => setSkillModalOpen(false)}
        >
          <div
            className="model-tester-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="model-tester-skill-md-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="model-tester-modal-header">
              <h2 id="model-tester-skill-md-title" className="model-tester-modal-title">
                Skill: {skillModalTitle || '—'}
              </h2>
              <button
                type="button"
                className="model-tester-modal-close"
                aria-label="Close"
                onClick={() => setSkillModalOpen(false)}
              >
                ✕
              </button>
            </div>
            {skillModalLoading ? (
              <div className="model-tester-modal-body">Loading SKILL.md…</div>
            ) : skillModalError ? (
              <div className="model-tester-modal-body">{skillModalError}</div>
            ) : (
              <pre className="model-tester-modal-body">{skillModalBody}</pre>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default ModelTester;
