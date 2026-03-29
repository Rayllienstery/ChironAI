import React, { useMemo, useState, useEffect } from 'react';
import { getModels, getPrompts, getModelSettings, updateModelSettings, getRagCollections } from '../services/api';
import { isLogicalRagModelId } from '../constants/llmProxyModels';
import './ModelSettings.css';

function ModelSettings({ sessionId, onOpenRagModels }) {
  const [models, setModels] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [collections, setCollections] = useState([]);
  const [settings, setSettings] = useState({
    model: '',
    prompt_name: '',
    temperature: 0.0,
    top_p: 0.1,
    reasoning_level: '',
    code_only: false,
    include_rag_metadata: true,
    fetch_web_knowledge: false,
    web_interaction_enabled: false,
    web_interaction_on_keywords: true,
    web_interaction_on_low_confidence_framework: true,
    rag_collection: '',
    rerank_for_rag: false,
    rerank_model: '',
    model_missing: false,
    prompt_missing: false,
    collection_missing: false,
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [modelsData, promptsData, settingsData, collectionsData] = await Promise.all([
        getModels(),
        getPrompts(),
        getModelSettings(),
        getRagCollections().catch(() => ({ collections: [] })),
      ]);

      setModels(modelsData);
      const promptList = (promptsData.prompts || []).filter(
        (p) => p.name && p.name.toLowerCase() !== 'readme'
      );
      setPrompts(promptList);
      setCollections(collectionsData?.collections || []);

      if (settingsData) {
        setSettings((prev) => {
          const next = { ...prev, ...settingsData };
          delete next.proxy_tool_policy;
          delete next.proxy_stateful_guards;
          delete next.proxy_text_tool_retries;
          return next;
        });
      }
    } catch (error) {
      console.error('Failed to load data:', error);
    } finally {
      setLoading(false);
    }
  };

  const ollamaModels = useMemo(
    () => models.filter((m) => !isLogicalRagModelId(m.id)),
    [models]
  );
  const modelIds = useMemo(() => ollamaModels.map((m) => m.id), [ollamaModels]);
  const promptNames = useMemo(() => prompts.map((p) => p.name).filter(Boolean), [prompts]);
  const collectionNames = useMemo(() => collections.map((c) => c.name).filter(Boolean), [collections]);

  const validationIssues = useMemo(() => {
    const issues = [];
    const m = (settings.model || '').trim();
    const pn = (settings.prompt_name || '').trim();
    const rc = (settings.rag_collection || '').trim();

    const modelInList = Boolean(m && modelIds.includes(m));
    const modelInvalid =
      !m ||
      isLogicalRagModelId(m) ||
      (modelIds.length > 0 && !modelInList);

    if (modelInvalid) {
      if (m && modelIds.length > 0 && !modelInList) {
        issues.push(`Model: saved value "${m}" is not in the current Ollama list — pick an available model.`);
      } else {
        issues.push('Model: select a concrete Ollama model (not ChironAI-Worker).');
      }
    }

    const promptOk = Boolean(pn && promptNames.includes(pn));
    // Do not use stale API flag prompt_missing once the user picks a name from the current list.
    if (!promptOk) {
      if (promptNames.length === 0 && pn) {
        issues.push('Prompt template: list failed to load — refresh the page or check /api/webui/prompts.');
      } else if (pn && promptNames.length > 0 && !promptNames.includes(pn)) {
        issues.push(`Prompt template: "${pn}" is not in the current prompts/*.md list — pick another name.`);
      } else if (!pn) {
        issues.push('Prompt template: select a valid template from the list.');
      }
    }

    if (collectionNames.length === 0) {
      issues.push('RAG collection: no Qdrant collections found — create one under RAG / Qdrant.');
    } else {
      if (!rc) {
        issues.push('RAG collection: select a collection (required for LLM Proxy).');
      } else if (!collectionNames.includes(rc)) {
        issues.push(
          `RAG collection: "${rc}" is missing or not in Qdrant — pick another collection.`
        );
      }
    }

    return issues;
  }, [settings, modelIds, promptNames, collectionNames]);

  const handleChange = (field, value) => {
    setSettings((prev) => {
      const next = { ...prev, [field]: value };
      if (field === 'prompt_name') {
        next.prompt_missing = false;
      }
      if (field === 'model') {
        next.model_missing = false;
      }
      if (field === 'rag_collection') {
        next.collection_missing = false;
      }
      return next;
    });
  };

  const handleSave = async () => {
    if (validationIssues.length > 0) {
      window.alert('Fix the configuration errors shown in red before saving.');
      return;
    }
    setSaving(true);
    try {
      await updateModelSettings(settings);
      window.alert('Settings saved successfully');
      await loadData();
    } catch (error) {
      console.error('Failed to save settings:', error);
      window.alert('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const modelSelectValue = modelIds.includes((settings.model || '').trim()) ? settings.model : '';
  const promptSelectValue = promptNames.includes((settings.prompt_name || '').trim())
    ? settings.prompt_name
    : '';
  const collectionSelectValue =
    collectionNames.length > 0 && collectionNames.includes((settings.rag_collection || '').trim())
      ? settings.rag_collection
      : '';

  if (loading) {
    return <div className="loading">Loading settings...</div>;
  }

  return (
    <div className="model-settings">
      {validationIssues.length > 0 && (
        <div className="settings-error-banner" role="alert">
          <strong>Configuration errors</strong>
          <ul>
            {validationIssues.map((msg) => (
              <li key={msg}>{msg}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="settings-form">
        <div className="form-group">
          <label>Model</label>
          <select
            value={modelSelectValue}
            onChange={(e) => handleChange('model', e.target.value)}
          >
            <option value="">Select Ollama model…</option>
            {ollamaModels.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
          {(settings.model || '').trim() &&
            !modelIds.includes((settings.model || '').trim()) &&
            modelIds.length > 0 && (
              <p className="settings-stale-value">
                Saved in database: <code>{settings.model}</code> (not in current Ollama list)
              </p>
            )}
        </div>

        <div className="form-group">
          <label>Prompt Template</label>
          <select
            value={promptSelectValue}
            onChange={(e) => handleChange('prompt_name', e.target.value)}
          >
            <option value="">Select prompt template…</option>
            {prompts
              .filter((prompt) => prompt.name && prompt.name.toLowerCase() !== 'readme')
              .map((prompt) => (
                <option key={prompt.id || prompt.name} value={prompt.name}>
                  {prompt.name}
                </option>
              ))}
          </select>
          {(settings.prompt_name || '').trim() &&
            !promptNames.includes((settings.prompt_name || '').trim()) && (
              <p className="settings-stale-value">
                Saved in database: <code>{settings.prompt_name}</code> (file missing or not in list)
              </p>
            )}
        </div>

        <div className="form-group">
          <label>
            Temperature: {Number(settings.temperature || 0).toFixed(1)}
          </label>
          <input
            type="range"
            min="0"
            max="20"
            step="0.1"
            value={Number(settings.temperature || 0) * 10}
            onChange={(e) => handleChange('temperature', parseFloat(e.target.value) / 10)}
          />
        </div>

        <div className="form-group">
          <label>
            Top-p: {Number(settings.top_p || 0).toFixed(1)}
          </label>
          <input
            type="range"
            min="0"
            max="10"
            step="0.1"
            value={Number(settings.top_p || 0) * 10}
            onChange={(e) => handleChange('top_p', parseFloat(e.target.value) / 10)}
          />
        </div>

        <div className="form-group">
          <label>Reasoning Level</label>
          <select
            value={settings.reasoning_level}
            onChange={(e) => handleChange('reasoning_level', e.target.value)}
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
              checked={settings.code_only}
              onChange={(e) => handleChange('code_only', e.target.checked)}
            />
            Code only
          </label>
        </div>

        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.include_rag_metadata}
              onChange={(e) => handleChange('include_rag_metadata', e.target.checked)}
            />
            Include RAG metadata
          </label>
        </div>

        <div className="form-group">
          <label>RAG Collection</label>
          <select
            value={collectionSelectValue}
            onChange={(e) => handleChange('rag_collection', e.target.value)}
            disabled={collections.length === 0}
          >
            {collections.length === 0 ? (
              <option value="">No collections — create one in RAG / Qdrant</option>
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
          <p className="setting-hint">
            Qdrant collection used for LLM Proxy RAG (required).
          </p>
          {(settings.rag_collection || '').trim() &&
            collectionNames.length > 0 &&
            !collectionNames.includes((settings.rag_collection || '').trim()) && (
              <p className="settings-stale-value">
                Saved in database: <code>{settings.rag_collection}</code> (not in current list)
              </p>
            )}
        </div>

        <div className="form-group checkbox-group">
          <label>
            <input
              type="checkbox"
              checked={settings.rerank_for_rag}
              onChange={(e) => handleChange('rerank_for_rag', e.target.checked)}
            />
            Rerank for RAG
          </label>
          <p className="setting-warning">
            Improves answer quality but slows down requests; ideally use a dedicated rerank model.
          </p>
        </div>

        <div className="form-group">
          <label>Rerank Model</label>
          {typeof onOpenRagModels === 'function' ? (
            <>
              <button
                type="button"
                className="navigate-rag-models-button"
                onClick={onOpenRagModels}
              >
                Open RAG / Qdrant — Models for RAG / Qdrant
              </button>
              <p className="setting-hint">
                Embedding and rerank models are configured on the <strong>RAG / Qdrant</strong> tab under
                &quot;Models for RAG / Qdrant&quot;.
              </p>
            </>
          ) : (
            <>
              <select
                value={settings.rerank_model ?? ''}
                onChange={(e) => handleChange('rerank_model', e.target.value)}
              >
                <option value="">No rerank model override</option>
                {ollamaModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
              <p className="setting-hint">
                Model used for reranking when &quot;Rerank for RAG&quot; is on.
              </p>
            </>
          )}
        </div>

        <button
          className="save-button"
          onClick={handleSave}
          disabled={saving || validationIssues.length > 0}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  );
}

export default ModelSettings;
