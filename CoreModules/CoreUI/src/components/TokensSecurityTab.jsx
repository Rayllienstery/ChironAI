import { useCallback, useEffect, useState } from 'react';
import CoreUIButton from './CoreUIButton';
import {
  deleteLlmProxyApiKey,
  generateLlmProxyApiKey,
  getLlmProxyApiKeyStatus,
  revealLlmProxyApiKey,
} from '../services/api';
import '../styles/components/SettingsTab.css';
import '../styles/components/DashboardTab.css';
import '../styles/components/LlmProxyTab.css';

function kvRow(label, value, key) {
  return (
    <div className="dashboard-kv-row" key={key}>
      <span className="dashboard-kv-label">{label}</span>
      <span className="dashboard-kv-value">{value}</span>
    </div>
  );
}

function formatApiKeyDate(value) {
  if (!value) return 'Never';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function TokensSecurityTab() {
  const [apiKeyStatus, setApiKeyStatus] = useState(null);
  const [apiKeyErr, setApiKeyErr] = useState(null);
  const [apiKeyBusy, setApiKeyBusy] = useState(false);
  const [generatedApiKey, setGeneratedApiKey] = useState('');
  const [copyState, setCopyState] = useState('');

  const refreshApiKeyStatus = useCallback(async () => {
    setApiKeyErr(null);
    setApiKeyBusy(true);
    setGeneratedApiKey('');
    setCopyState('');
    try {
      const s = await getLlmProxyApiKeyStatus();
      setApiKeyStatus(s);
    } catch (e) {
      setApiKeyStatus(null);
      setApiKeyErr(String(e.message || e));
    } finally {
      setApiKeyBusy(false);
    }
  }, []);

  const handleGenerateApiKey = useCallback(async () => {
    if (
      apiKeyStatus?.configured &&
      !window.confirm('Regenerate the Chiron proxy API key? Existing clients will stop working.')
    ) {
      return;
    }
    setApiKeyErr(null);
    setApiKeyBusy(true);
    setCopyState('');
    try {
      const data = await generateLlmProxyApiKey();
      setApiKeyStatus({
        configured: data.configured,
        prefix: data.prefix,
        created_at: data.created_at,
        rotated_at: data.rotated_at,
        recoverable: data.recoverable,
      });
      setGeneratedApiKey(data.key || '');
    } catch (e) {
      setApiKeyErr(String(e.message || e));
    } finally {
      setApiKeyBusy(false);
    }
  }, [apiKeyStatus?.configured]);

  const handleRevealApiKey = useCallback(async () => {
    setApiKeyErr(null);
    setApiKeyBusy(true);
    setCopyState('');
    try {
      const data = await revealLlmProxyApiKey();
      setApiKeyStatus({
        configured: data.configured,
        prefix: data.prefix,
        created_at: data.created_at,
        rotated_at: data.rotated_at,
        recoverable: data.recoverable,
      });
      setGeneratedApiKey(data.key || '');
    } catch (e) {
      setApiKeyErr(String(e.message || e));
    } finally {
      setApiKeyBusy(false);
    }
  }, []);

  const handleDeleteApiKey = useCallback(async () => {
    if (!window.confirm('Delete the Chiron proxy API key? Protected /v1 routes will close until a new key is generated.')) {
      return;
    }
    setApiKeyErr(null);
    setApiKeyBusy(true);
    setCopyState('');
    try {
      const data = await deleteLlmProxyApiKey();
      setApiKeyStatus(data);
      setGeneratedApiKey('');
    } catch (e) {
      setApiKeyErr(String(e.message || e));
    } finally {
      setApiKeyBusy(false);
    }
  }, []);

  const handleCopyApiKey = useCallback(async () => {
    if (!generatedApiKey) return;
    try {
      await navigator.clipboard.writeText(generatedApiKey);
      setCopyState('Copied');
    } catch {
      setCopyState('Copy failed');
    }
  }, [generatedApiKey]);

  useEffect(() => {
    refreshApiKeyStatus();
  }, [refreshApiKeyStatus]);

  return (
    <div className="settings-tab settings-tab--fullwidth llm-proxy-tab tab-view">
      <div className="llm-proxy-header">
        <div className="llm-proxy-header-row">
          <h2>Tokens and Security</h2>
        </div>
      </div>

      <div className="settings-form">
        <section className="app-default-card llm-proxy-status-card" aria-labelledby="tokens-security-api-key-heading">
          <div className="dashboard-card-header">
            <h2 id="tokens-security-api-key-heading">Security</h2>
            <div className="dashboard-card-actions">
              <CoreUIButton variant="primary" onClick={refreshApiKeyStatus} disabled={apiKeyBusy}>
                Refresh
              </CoreUIButton>
            </div>
          </div>
          {!apiKeyStatus && !apiKeyErr && <p className="dashboard-card-muted">Loading...</p>}
          {apiKeyErr && <div className="dashboard-card-error">{apiKeyErr}</div>}
          {apiKeyStatus && (
            <>
              {kvRow('API key', apiKeyStatus.configured ? 'Configured' : 'Not configured', 'api-key-configured')}
              {kvRow('Prefix', apiKeyStatus.prefix ? <code>{apiKeyStatus.prefix}</code> : 'None', 'api-key-prefix')}
              {kvRow('Created', formatApiKeyDate(apiKeyStatus.created_at), 'api-key-created')}
              {kvRow('Rotated', formatApiKeyDate(apiKeyStatus.rotated_at), 'api-key-rotated')}
              {kvRow('Recoverable', apiKeyStatus.recoverable ? 'Yes' : 'No', 'api-key-recoverable')}

              {generatedApiKey && (
                <div className="llm-proxy-generated-key">
                  <div className="llm-proxy-generated-key-row">
                    <code>{generatedApiKey}</code>
                    <CoreUIButton variant="primary" onClick={handleCopyApiKey}>
                      Copy key
                    </CoreUIButton>
                  </div>
                  <p className="dashboard-card-muted">
                    Store it in your OpenAI-compatible client, IDE, or OpenWebUI provider settings.
                  </p>
                  {copyState && <p className="llm-proxy-copy-state">{copyState}</p>}
                </div>
              )}

              <div className="dashboard-card-actions llm-proxy-api-key-actions">
                <CoreUIButton variant="primary" onClick={handleGenerateApiKey} disabled={apiKeyBusy}>
                  {apiKeyStatus.configured ? 'Regenerate key' : 'Generate key'}
                </CoreUIButton>
                {apiKeyStatus.configured && apiKeyStatus.recoverable && (
                  <CoreUIButton variant="primary" onClick={handleRevealApiKey} disabled={apiKeyBusy}>
                    Reveal key
                  </CoreUIButton>
                )}
                {apiKeyStatus.configured && (
                  <CoreUIButton variant="danger" onClick={handleDeleteApiKey} disabled={apiKeyBusy}>
                    Delete key
                  </CoreUIButton>
                )}
              </div>
            </>
          )}
        </section>
      </div>
    </div>
  );
}

export default TokensSecurityTab;
