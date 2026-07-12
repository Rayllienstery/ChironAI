import { useCallback, useEffect, useMemo, useState } from 'react';
import CoreUIButton from './CoreUIButton';
import CoreUIModal from './CoreUIModal';
import {
  changeRevealPin,
  deleteLlmProxyApiKey,
  disableRevealPin,
  generateLlmProxyApiKey,
  getLlmProxyApiKeyStatus,
  getRevealPinStatus,
  revealLlmProxyApiKey,
  resetRevealPinLockout,
  setRevealPin,
} from '../services/api';
import '../styles/components/SettingsTab.css';
import '../styles/components/DashboardTab.css';
import '../styles/components/LlmProxyTab.css';
import { setRemoteRevealPin } from '../services/remoteRevealPin.js';
import { isLoopbackHost } from '../utils/loopbackHost.js';

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

const PIN_MODES = {
  INSTALL: 'install',
  CHANGE: 'change',
  DISABLE: 'disable',
  REVEAL: 'reveal',
};

function TokensSecurityTab() {
  const [apiKeyStatus, setApiKeyStatus] = useState(null);
  const [apiKeyErr, setApiKeyErr] = useState(null);
  const [apiKeyBusy, setApiKeyBusy] = useState(false);
  const [generatedApiKey, setGeneratedApiKey] = useState('');
  const [copyState, setCopyState] = useState('');

  const [pinStatus, setPinStatus] = useState(null);
  const [pinStatusErr, setPinStatusErr] = useState(null);
  const [pinBusy, setPinBusy] = useState(false);

  const [pinModalOpen, setPinModalOpen] = useState(false);
  const [pinModalMode, setPinModalMode] = useState(PIN_MODES.INSTALL);
  const [pinInput, setPinInput] = useState('');
  const [currentPinInput, setCurrentPinInput] = useState('');
  const [newPinInput, setNewPinInput] = useState('');
  const [pinErr, setPinErr] = useState(null);

  const isLoopback = useMemo(() => isLoopbackHost(), []);

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

  const refreshPinStatus = useCallback(async () => {
    setPinStatusErr(null);
    try {
      const s = await getRevealPinStatus();
      setPinStatus(s);
      return s;
    } catch (e) {
      setPinStatus(null);
      setPinStatusErr(String(e.message || e));
      return null;
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

  const finishReveal = useCallback(async (pin = null) => {
    setApiKeyErr(null);
    setApiKeyBusy(true);
    setCopyState('');
    try {
      const data = await revealLlmProxyApiKey(pin);
      setApiKeyStatus({
        configured: data.configured,
        prefix: data.prefix,
        created_at: data.created_at,
        rotated_at: data.rotated_at,
        recoverable: data.recoverable,
      });
      setGeneratedApiKey(data.key || '');
      return true;
    } catch (e) {
      setApiKeyErr(String(e.message || e));
      return false;
    } finally {
      setApiKeyBusy(false);
    }
  }, []);

  const handleRevealApiKey = useCallback(async () => {
    if (isLoopback) {
      await finishReveal();
      return;
    }
    let status = pinStatus;
    if (!status) {
      status = await refreshPinStatus();
    }
    if (status?.locked_out) {
      return;
    }
    if (!status?.configured) {
      setApiKeyErr(
        'Remote reveal requires a PIN. Install one from the local machine first (Tokens and Security → Remote Access).',
      );
      return;
    }
    setPinInput('');
    setPinErr(null);
    setPinModalMode(PIN_MODES.REVEAL);
    setPinModalOpen(true);
  }, [isLoopback, pinStatus, refreshPinStatus, finishReveal]);

  const handleRevealWithPin = useCallback(async () => {
    setPinErr(null);
    setRemoteRevealPin(pinInput);
    const ok = await finishReveal(pinInput);
    if (ok) {
      setPinModalOpen(false);
      setPinInput('');
    }
    await refreshPinStatus();
  }, [pinInput, finishReveal, refreshPinStatus]);

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

  const openPinModal = useCallback((mode) => {
    setPinInput('');
    setCurrentPinInput('');
    setNewPinInput('');
    setPinErr(null);
    setPinModalMode(mode);
    setPinModalOpen(true);
  }, []);

  const closePinModal = useCallback(() => {
    setPinModalOpen(false);
    setPinInput('');
    setCurrentPinInput('');
    setNewPinInput('');
    setPinErr(null);
  }, []);

  const handlePinSubmit = useCallback(async () => {
    setPinErr(null);
    setPinBusy(true);
    try {
      if (pinModalMode === PIN_MODES.INSTALL) {
        await setRevealPin(pinInput);
      } else if (pinModalMode === PIN_MODES.CHANGE) {
        await changeRevealPin(currentPinInput, newPinInput);
      } else if (pinModalMode === PIN_MODES.DISABLE) {
        await disableRevealPin(pinInput);
      } else if (pinModalMode === PIN_MODES.REVEAL) {
        await handleRevealWithPin();
        return;
      }
      closePinModal();
      await refreshPinStatus();
    } catch (e) {
      setPinErr(String(e.message || e));
    } finally {
      setPinBusy(false);
    }
  }, [
    pinModalMode,
    pinInput,
    currentPinInput,
    newPinInput,
    handleRevealWithPin,
    refreshPinStatus,
    closePinModal,
  ]);

  const handleResetLockout = useCallback(async () => {
    if (!window.confirm('Reset the reveal PIN lockout? This allows remote reveal attempts to resume.')) {
      return;
    }
    setPinBusy(true);
    setPinErr(null);
    try {
      await resetRevealPinLockout();
      await refreshPinStatus();
    } catch (e) {
      setPinErr(String(e.message || e));
    } finally {
      setPinBusy(false);
    }
  }, [refreshPinStatus]);

  useEffect(() => {
    refreshApiKeyStatus();
    refreshPinStatus();
  }, [refreshApiKeyStatus, refreshPinStatus]);

  const pinModalTitle = useMemo(() => {
    switch (pinModalMode) {
      case PIN_MODES.INSTALL:
        return 'Install remote reveal PIN';
      case PIN_MODES.CHANGE:
        return 'Change remote reveal PIN';
      case PIN_MODES.DISABLE:
        return 'Disable remote reveal PIN';
      case PIN_MODES.REVEAL:
        return 'Enter remote reveal PIN';
      default:
        return 'Remote reveal PIN';
    }
  }, [pinModalMode]);

  const canSubmitPin = useMemo(() => {
    if (pinModalMode === PIN_MODES.CHANGE) {
      return currentPinInput.length >= 4 && newPinInput.length >= 4;
    }
    return pinInput.length >= 4;
  }, [pinModalMode, pinInput, currentPinInput, newPinInput]);

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

        <section className="app-default-card remote-access-card" aria-labelledby="remote-access-heading">
          <div className="dashboard-card-header">
            <h2 id="remote-access-heading">Remote Access</h2>
            <div className="dashboard-card-actions">
              <CoreUIButton variant="primary" onClick={refreshPinStatus} disabled={pinBusy}>
                Refresh
              </CoreUIButton>
            </div>
          </div>
          {pinStatusErr && <div className="dashboard-card-error">{pinStatusErr}</div>}
          {!pinStatus && !pinStatusErr && <p className="dashboard-card-muted">Loading...</p>}
          {pinStatus && (
            <>
              {kvRow(
                'Remote reveal PIN',
                pinStatus.configured ? 'Configured' : 'Not configured',
                'remote-pin-configured',
              )}
              {kvRow(
                'LAN reveal status',
                pinStatus.locked_out ? 'Locked out' : 'Allowed',
                'remote-pin-locked-out',
              )}

              {pinStatus.locked_out && (
                <div className="lockout-alert" role="alert">
                  <span className="material-symbols-outlined" aria-hidden="true">warning</span>
                  <p>
                    PIN is locked. To reset the PIN, open ChironAI WebUI on the machine where the
                    server is running (<code>http://127.0.0.1:&lt;port&gt;/webui</code>) and use{' '}
                    <strong>Reset PIN</strong> in Tokens and Security → Remote Access.
                  </p>
                </div>
              )}

              <div className="dashboard-card-actions remote-access-actions">
                {isLoopback ? (
                  <>
                    {!pinStatus.configured && (
                      <CoreUIButton variant="primary" onClick={() => openPinModal(PIN_MODES.INSTALL)} disabled={pinBusy}>
                        Install PIN
                      </CoreUIButton>
                    )}
                    {pinStatus.configured && (
                      <>
                        <CoreUIButton variant="primary" onClick={() => openPinModal(PIN_MODES.CHANGE)} disabled={pinBusy}>
                          Change PIN
                        </CoreUIButton>
                        <CoreUIButton variant="danger" onClick={() => openPinModal(PIN_MODES.DISABLE)} disabled={pinBusy}>
                          Disable PIN
                        </CoreUIButton>
                      </>
                    )}
                    {pinStatus.locked_out && (
                      <CoreUIButton variant="primary" onClick={handleResetLockout} disabled={pinBusy}>
                        Reset Lockout
                      </CoreUIButton>
                    )}
                  </>
                ) : (
                  <p className="dashboard-card-muted">
                    Install, change, or reset the reveal PIN from the machine where the server is running.
                  </p>
                )}
              </div>
            </>
          )}
        </section>
      </div>

      {pinModalOpen && (
        <CoreUIModal
          title={pinModalTitle}
          onClose={closePinModal}
          className="pin-modal"
          footer={
            <>
              <CoreUIButton variant="secondary" onClick={closePinModal} disabled={pinBusy}>
                Cancel
              </CoreUIButton>
              <CoreUIButton variant="primary" onClick={handlePinSubmit} disabled={pinBusy || !canSubmitPin}>
                {pinModalMode === PIN_MODES.REVEAL ? 'Reveal key' : 'Save'}
              </CoreUIButton>
            </>
          }
        >
          <div className="pin-modal-body">
            {pinModalMode === PIN_MODES.CHANGE ? (
              <>
                <label htmlFor="current-pin">Current PIN</label>
                <input
                  id="current-pin"
                  type="password"
                  inputMode="numeric"
                  pattern="\d{4,8}"
                  maxLength={8}
                  value={currentPinInput}
                  onChange={(e) => setCurrentPinInput(e.target.value.replace(/\D/g, '').slice(0, 8))}
                  placeholder="Current 4-8 digit PIN"
                  autoComplete="off"
                />
                <label htmlFor="new-pin">New PIN</label>
                <input
                  id="new-pin"
                  type="password"
                  inputMode="numeric"
                  pattern="\d{4,8}"
                  maxLength={8}
                  value={newPinInput}
                  onChange={(e) => setNewPinInput(e.target.value.replace(/\D/g, '').slice(0, 8))}
                  placeholder="New 4-8 digit PIN"
                  autoComplete="off"
                />
              </>
            ) : (
              <>
                <label htmlFor="pin-input">
                  {pinModalMode === PIN_MODES.REVEAL ? 'PIN' : '4-8 digit PIN'}
                </label>
                <input
                  id="pin-input"
                  type="password"
                  inputMode="numeric"
                  pattern="\d{4,8}"
                  maxLength={8}
                  value={pinInput}
                  onChange={(e) => setPinInput(e.target.value.replace(/\D/g, '').slice(0, 8))}
                  placeholder="Enter PIN"
                  autoComplete="off"
                />
              </>
            )}
            {pinErr && <div className="pin-error">{pinErr}</div>}
            {pinModalMode !== PIN_MODES.REVEAL && (
              <p className="dashboard-card-muted">
                The PIN is required to reveal the proxy API key or view logs from a LAN client. It is not stored in the browser.
              </p>
            )}
          </div>
        </CoreUIModal>
      )}
    </div>
  );
}

export default TokensSecurityTab;
