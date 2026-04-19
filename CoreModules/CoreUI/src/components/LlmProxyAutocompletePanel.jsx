import { useMemo, useState, useEffect } from 'react';
import { getModels, getModelSettings, updateModelSettings } from '../services/api';
import { isLogicalRagModelId } from '../constants/llmProxyModels';
import CoreUIButton from './CoreUIButton';
import '../styles/components/ModelSettings.css';

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
          Logical id <code>{LOGICAL_AUTOCOMPLETE_ID}</code> in <code>GET /v1/models</code> maps to the Ollama model you
          pick below. <strong>Assistant chat</strong> still uses the WebUI prompt template, RAG, and{' '}
          <code>POST /v1/chat/completions</code>. <strong>Zed edit prediction</strong> uses{' '}
          <code>POST /v1/completions</code>, which the proxy forwards to native Ollama <code>/api/generate</code> (same as
          connecting Zed straight to Ollama): no RAG, no web supplement, no template file — only the prompt Zed sends.
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
        <CoreUIButton variant="primary" className="save-button" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving…' : 'Save'}
        </CoreUIButton>
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
            <strong>Edit prediction</strong> (OpenAI-compatible): set API URL to{' '}
            <code>
              http://&lt;host&gt;:&lt;port&gt;/v1/completions
            </code>{' '}
            — proxied to Ollama <code>/api/generate</code>; not <code>/v1/chat/completions</code>.
          </li>
          <li>
            Assistant <strong>chat</strong>: proxy base URL without trailing <code>/v1</code> (see{' '}
            <strong>RAG Fusion Proxy</strong> → <strong>Overview</strong>).
          </li>
          <li>
            Provider: <em>OpenAI-compatible</em>. API key empty unless you added auth on the proxy.
          </li>
          <li>
            Assistant / chat: use your <strong>build id</strong> from <strong>LLM Proxy</strong> → <strong>Builds</strong> as{' '}
            <code>model</code> (same proxy base URL as in <strong>RAG Fusion Proxy</strong> → <strong>Overview</strong>).
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
