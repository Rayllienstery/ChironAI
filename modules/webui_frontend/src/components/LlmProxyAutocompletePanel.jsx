import React, { useMemo, useState, useEffect } from 'react';
import { getModels, getModelSettings, updateModelSettings } from '../services/api';
import { isLogicalRagModelId } from '../constants/llmProxyModels';
import './ModelSettings.css';

const LOGICAL_AUTOCOMPLETE_ID = 'ChironAI-Autocomplete';

function LlmProxyAutocompletePanel() {
  const [models, setModels] = useState([]);
  const [autocompleteModel, setAutocompleteModel] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [modelsData, settingsData] = await Promise.all([getModels(), getModelSettings()]);
        if (cancelled) return;
        setModels(modelsData || []);
        if (settingsData && settingsData.autocomplete_model != null) {
          setAutocompleteModel(String(settingsData.autocomplete_model || '').trim());
        }
      } catch (e) {
        console.error('Failed to load autocomplete settings:', e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const ollamaModels = useMemo(
    () => (models || []).filter((m) => !isLogicalRagModelId(m.id)),
    [models]
  );
  const modelIds = useMemo(() => ollamaModels.map((m) => m.id), [ollamaModels]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateModelSettings({ autocomplete_model: autocompleteModel });
      window.alert('Autocomplete settings saved.');
    } catch (e) {
      console.error(e);
      window.alert('Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const selectValue = modelIds.includes((autocompleteModel || '').trim()) ? autocompleteModel : '';

  if (loading) {
    return <div className="loading">Loading…</div>;
  }

  return (
    <div className="settings-form model-settings">
      <div className="settings-section">
        <h3>Autocomplete model</h3>
        <p className="settings-intro">
          Inline completions use the same OpenAI-compatible proxy as chat: logical model id{' '}
          <code>{LOGICAL_AUTOCOMPLETE_ID}</code> in <code>GET /v1/models</code> and{' '}
          <code>POST /v1/chat/completions</code>. No RAG — use a small, fast Ollama model here. Chat continues to use{' '}
          <code>ChironAI-Worker</code> with your main model and RAG.
        </p>
        <div className="form-group">
          <label htmlFor="autocomplete-model-select">Ollama model for autocomplete</label>
          <select
            id="autocomplete-model-select"
            value={selectValue}
            onChange={(e) => setAutocompleteModel(e.target.value)}
          >
            <option value="">None (hide {LOGICAL_AUTOCOMPLETE_ID} from /v1/models)</option>
            {ollamaModels.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
          {(autocompleteModel || '').trim() &&
            modelIds.length > 0 &&
            !modelIds.includes((autocompleteModel || '').trim()) && (
              <p className="settings-stale-value">
                Saved: <code>{autocompleteModel}</code> (not in current Ollama list)
              </p>
            )}
        </div>
        <button type="button" className="save-button" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </button>
      </div>

      <div className="settings-section">
        <h3>Recommendations</h3>
        <ul className="settings-instructions">
          <li>Pick a smaller instruct or code model than your main chat model to keep latency low.</li>
          <li>If completions are slow, try a lower-quantization variant or a smaller tag.</li>
          <li>Leave autocomplete empty if you only need assistant chat with RAG.</li>
        </ul>
      </div>

      <div className="settings-section">
        <h3>Zed (chat + autocomplete)</h3>
        <ol className="settings-instructions">
          <li>
            Use the proxy base URL (same host/port as ChironAI), without trailing <code>/v1</code>.
          </li>
          <li>
            Provider: <em>OpenAI-compatible</em>. API key empty unless you added auth on the proxy.
          </li>
          <li>
            Assistant / chat: model <code>ChironAI-Worker</code> (after configuring main model in Overview → Model Settings).
          </li>
          <li>
            Inline assistant / completions: model <code>{LOGICAL_AUTOCOMPLETE_ID}</code> after you save an Ollama model
            above and it appears in <code>/v1/models</code>.
          </li>
        </ol>
      </div>
    </div>
  );
}

export default LlmProxyAutocompletePanel;
