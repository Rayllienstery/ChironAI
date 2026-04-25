import { useMemo, useState, useEffect } from 'react';
import { getProviderCatalog, getModelSettings, updateModelSettings } from '../services/api';
import { isLogicalRagModelId } from '../constants/llmProxyModels';
import CoreUIButton from './CoreUIButton';
import '../styles/components/ModelSettings.css';

const LOGICAL_AUTOCOMPLETE_ID = 'ChironAI-Autocomplete';

function LlmProxyAutocompletePanel() {
  const [catalog, setCatalog] = useState({ providers: [], models: [] });
  const [autocompleteProviderId, setAutocompleteProviderId] = useState('');
  const [autocompleteModel, setAutocompleteModel] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [catalogData, settingsData] = await Promise.all([
          getProviderCatalog('chat'),
          getModelSettings(),
        ]);
        if (cancelled) return;
        setCatalog({
          providers: Array.isArray(catalogData?.providers) ? catalogData.providers : [],
          models: Array.isArray(catalogData?.models) ? catalogData.models : [],
        });
        if (settingsData && settingsData.autocomplete_provider_id != null) {
          setAutocompleteProviderId(String(settingsData.autocomplete_provider_id || '').trim());
        }
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

  const providers = useMemo(() => catalog.providers || [], [catalog]);
  const filteredModels = useMemo(
    () =>
      (catalog.models || []).filter(
        (model) =>
          !isLogicalRagModelId(model.id) &&
          (!autocompleteProviderId || String(model.provider_id || '').trim() === autocompleteProviderId),
      ),
    [autocompleteProviderId, catalog],
  );
  const modelIds = useMemo(() => filteredModels.map((m) => m.id), [filteredModels]);

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateModelSettings({
        autocomplete_provider_id: autocompleteProviderId,
        autocomplete_model: autocompleteModel,
      });
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
    return <div className="loading">Loading...</div>;
  }

  return (
    <div className="settings-form model-settings">
      <div className="settings-section">
        <h3>Autocomplete model</h3>
        <p className="settings-intro">
          Logical id <code>{LOGICAL_AUTOCOMPLETE_ID}</code> in <code>GET /v1/models</code> maps to the provider/model pair you
          pick below. <strong>Assistant chat</strong> still uses the WebUI prompt template, RAG, and{' '}
          <code>POST /v1/chat/completions</code>. <strong>Zed edit prediction</strong> uses{' '}
          <code>POST /v1/completions</code>; today this path is still best with providers that support native completion-style
          generation.
        </p>
        <div className="form-group">
          <label htmlFor="autocomplete-provider-select">Provider for autocomplete</label>
          <select
            id="autocomplete-provider-select"
            value={autocompleteProviderId}
            onChange={(e) => {
              setAutocompleteProviderId(e.target.value);
              setAutocompleteModel('');
            }}
          >
            <option value="">Select provider...</option>
            {providers.map((provider) => (
              <option key={provider.provider_id} value={provider.provider_id}>
                {provider.title || provider.provider_id}
              </option>
            ))}
          </select>
        </div>
        <div className="form-group">
          <label htmlFor="autocomplete-model-select">Model for autocomplete</label>
          <select
            id="autocomplete-model-select"
            value={selectValue}
            onChange={(e) => setAutocompleteModel(e.target.value)}
          >
            <option value="">None (hide {LOGICAL_AUTOCOMPLETE_ID} from /v1/models)</option>
            {filteredModels.map((model) => (
              <option key={model.id} value={model.id}>
                {model.name}
              </option>
            ))}
          </select>
          {(autocompleteModel || '').trim() &&
            modelIds.length > 0 &&
            !modelIds.includes((autocompleteModel || '').trim()) && (
              <p className="settings-stale-value">
                Saved: <code>{autocompleteModel}</code> (not in current provider list)
              </p>
            )}
        </div>
        <CoreUIButton variant="primary" className="save-button" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </CoreUIButton>
      </div>

      <div className="settings-section">
        <h3>Recommendations</h3>
        <ul className="settings-instructions">
          <li>Pick a smaller instruct or code model than your main chat build to keep latency low.</li>
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
            </code>.
          </li>
          <li>
            Assistant <strong>chat</strong>: proxy base URL without trailing <code>/v1</code> (see{' '}
            <strong>RAG Fusion Proxy</strong> {'->'} <strong>Overview</strong>).
          </li>
          <li>
            Provider: <em>OpenAI-compatible</em>. API key empty unless you added auth on the proxy.
          </li>
          <li>
            Assistant / chat: use your <strong>build id</strong> from <strong>LLM Proxy</strong> {'->'} <strong>Builds</strong> as{' '}
            <code>model</code>.
          </li>
          <li>
            Inline assistant / completions: model <code>{LOGICAL_AUTOCOMPLETE_ID}</code> after you save a provider/model pair
            above and it appears in <code>/v1/models</code>.
          </li>
        </ol>
      </div>
    </div>
  );
}

export default LlmProxyAutocompletePanel;
