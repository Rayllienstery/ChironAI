import React, { useCallback, useEffect, useState } from 'react';
import {
  getOpenWebUiStatus,
  getOpenWebUiConfig,
  putOpenWebUiBackendUrl,
  startOpenWebUi,
  stopOpenWebUi,
} from '../services/api';
import CoreUIButton from './CoreUIButton';
import '../styles/components/DashboardTab.css';
import '../styles/components/OpenWebUiTab.css';

const CONFIG_LABELS = [
  ['open_webui_host_url', 'Host URL'],
  ['open_webui_container_name', 'Container name'],
  ['open_webui_image', 'Docker image'],
  ['open_webui_host_port', 'Host port'],
  ['open_webui_container_port', 'Container port'],
];

function effectiveUrlToHostPort(effective, hintUrl) {
  const tryParse = (s) => {
    try {
      const u = new URL(s);
      return {
        host: u.hostname,
        port: u.port ? String(u.port) : '',
      };
    } catch {
      return null;
    }
  };
  return (
    tryParse(effective) ||
    tryParse(hintUrl) || { host: 'host.docker.internal', port: '8080' }
  );
}

function hostPortToBackendUrl(host, port) {
  const h = (host || '').trim();
  const p = (port || '').trim();
  if (!h) {
    return '';
  }
  if (p) {
    return `http://${h}:${p}`;
  }
  return `http://${h}`;
}

function OpenWebUiTab({ onErrorStateChange }) {
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(null);
  const [configErr, setConfigErr] = useState(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [statusBusy, setStatusBusy] = useState(false);
  const [lastActionOutput, setLastActionOutput] = useState(null);
  const [backendHost, setBackendHost] = useState('');
  const [backendPort, setBackendPort] = useState('');
  const [backendSaveBusy, setBackendSaveBusy] = useState(false);
  const [backendSaveMsg, setBackendSaveMsg] = useState(null);

  const refreshStatus = useCallback(async () => {
    try {
      const s = await getOpenWebUiStatus();
      setStatus(s);
    } catch (e) {
      setStatus({ running: false, error: e?.message || String(e) });
    }
  }, []);

  const refreshConfig = useCallback(async () => {
    setConfigLoading(true);
    setConfigErr(null);
    try {
      const c = await getOpenWebUiConfig();
      setConfig(c);
      const eff = c.open_webui_ollama_base_url_effective || c.open_webui_ollama_url_for_container || '';
      const hint = c.llm_proxy_ollama_base_hint || '';
      const { host, port } = effectiveUrlToHostPort(eff, hint);
      setBackendHost(host);
      setBackendPort(port);
    } catch (e) {
      setConfig(null);
      setConfigErr(e?.message || String(e));
    } finally {
      setConfigLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshConfig();
  }, [refreshStatus, refreshConfig]);

  const tabError = Boolean(
    (status?.error && !status?.running) || configErr,
  );
  useEffect(() => {
    onErrorStateChange?.(tabError);
  }, [tabError, onErrorStateChange]);

  const handleStartStop = async () => {
    setStatusBusy(true);
    setLastActionOutput(null);
    try {
      const running = Boolean(status?.running);
      const res = running ? await stopOpenWebUi() : await startOpenWebUi();
      if (res && res.ok === false && res.output) {
        setLastActionOutput(String(res.output));
      }
      await refreshStatus();
    } catch (e) {
      setLastActionOutput(e?.message || String(e));
    } finally {
      setStatusBusy(false);
    }
  };

  const openInBrowser = () => {
    const u = status?.url;
    if (u) window.open(u, '_blank', 'noopener,noreferrer');
  };

  const applyLlmProxyHint = () => {
    const hint = config?.llm_proxy_ollama_base_hint;
    if (!hint) return;
    const { host, port } = effectiveUrlToHostPort('', hint);
    setBackendHost(host);
    setBackendPort(port);
    setBackendSaveMsg(null);
  };

  const saveBackend = async () => {
    setBackendSaveBusy(true);
    setBackendSaveMsg(null);
    try {
      const url = hostPortToBackendUrl(backendHost, backendPort);
      if (!url) {
        setBackendSaveMsg('Host is required.');
        return;
      }
      await putOpenWebUiBackendUrl(url);
      setBackendSaveMsg('Saved. Start or restart Open WebUI to apply; the container may be recreated if the URL changed.');
      await refreshConfig();
    } catch (e) {
      setBackendSaveMsg(e?.message || String(e));
    } finally {
      setBackendSaveBusy(false);
    }
  };

  const resetBackendToDefault = async () => {
    setBackendSaveBusy(true);
    setBackendSaveMsg(null);
    try {
      await putOpenWebUiBackendUrl('');
      await refreshConfig();
      setBackendSaveMsg('Cleared saved URL; environment/default will be used on next start.');
    } catch (e) {
      setBackendSaveMsg(e?.message || String(e));
    } finally {
      setBackendSaveBusy(false);
    }
  };

  const running = Boolean(status?.running);
  const url = status?.url || null;
  const statusError = status?.error ? String(status.error) : null;
  const httpErr = status?.http_error ? String(status.http_error) : null;
  const httpStatus =
    status?.http_status != null && status.http_status !== ''
      ? String(status.http_status)
      : null;

  const backendSource = config?.open_webui_ollama_base_url_source;
  const backendHint = config?.llm_proxy_ollama_base_hint;

  return (
    <div className="dashboard-tab openwebui-tab tab-view">
      <div className="tab-page-header">
        <h2>Open WebUI</h2>
      </div>

      <section className="app-default-card" aria-labelledby="openwebui-status-heading">
        <div className="dashboard-card-header">
          <h2 id="openwebui-status-heading">Service</h2>
          <div className="dashboard-card-actions">
            <CoreUIButton
              onClick={refreshStatus}
              disabled={statusBusy}
            >
              Refresh
            </CoreUIButton>
            <CoreUIButton
              variant="primary"
              onClick={handleStartStop}
              disabled={statusBusy}
            >
              {running ? 'Stop service' : 'Start service'}
            </CoreUIButton>
          </div>
        </div>

        <div className="openwebui-tab__status-grid" role="status" aria-label="Open WebUI status">
          <div className="openwebui-tab__status-pill">
            <span className="dashboard-rag-status-label">Running</span>
            <span className="dashboard-rag-status-value">{running ? 'true' : 'false'}</span>
          </div>
          <div className="openwebui-tab__status-pill openwebui-tab__status-pill--wide">
            <span className="dashboard-rag-status-label">URL</span>
            <span className="dashboard-rag-status-value">{url || '—'}</span>
          </div>
          {httpStatus ? (
            <div className="openwebui-tab__status-pill">
              <span className="dashboard-rag-status-label">HTTP status</span>
              <span className="dashboard-rag-status-value">{httpStatus}</span>
            </div>
          ) : null}
          {httpErr ? (
            <div className="openwebui-tab__status-pill openwebui-tab__status-pill--wide">
              <span className="dashboard-rag-status-label">HTTP error</span>
              <span className="dashboard-rag-status-value">{httpErr}</span>
            </div>
          ) : null}
          {statusError ? (
            <div className="openwebui-tab__status-pill openwebui-tab__status-pill--wide">
              <span className="dashboard-rag-status-label">Error</span>
              <span className="dashboard-rag-status-value">{statusError}</span>
            </div>
          ) : null}
        </div>

        <div className="openwebui-tab__actions-row">
          <CoreUIButton
            onClick={openInBrowser}
            disabled={!running || !url}
          >
            Open in browser
          </CoreUIButton>
        </div>

        {lastActionOutput ? (
          <div className="dashboard-card-error" role="alert">
            {lastActionOutput}
          </div>
        ) : null}
      </section>

      <section className="app-default-card" aria-labelledby="openwebui-backend-heading">
        <div className="dashboard-card-header">
          <h2 id="openwebui-backend-heading">Chat backend (Ollama-compatible)</h2>
          <div className="dashboard-card-actions">
            <CoreUIButton
              onClick={applyLlmProxyHint}
              disabled={configLoading || !backendHint}
            >
              Use LLM Proxy default
            </CoreUIButton>
            <CoreUIButton
              onClick={resetBackendToDefault}
              disabled={configLoading || backendSaveBusy}
            >
              Clear saved (env/default)
            </CoreUIButton>
            <CoreUIButton
              variant="primary"
              onClick={saveBackend}
              disabled={configLoading || backendSaveBusy}
            >
              Save backend
            </CoreUIButton>
          </div>
        </div>
        <p className="openwebui-tab__config-hint">
          Open WebUI uses this as <code>OLLAMA_BASE_URL</code> inside Docker (direct Ollama or Chiron LLM Proxy{' '}
          <code>/api/*</code> passthrough). Changing it recreates the container on the next start if the URL
          differs. Effective value source:{' '}
          <strong>{backendSource || '—'}</strong>
          {backendHint ? (
            <>
              . Typical LLM Proxy from the container: <code>{backendHint}</code>
            </>
          ) : null}
          .
        </p>
        <div className="openwebui-tab__backend-grid">
          <label className="openwebui-tab__backend-field">
            <span className="openwebui-tab__backend-label">Host</span>
            <input
              type="text"
              className="dashboard-input"
              value={backendHost}
              onChange={(e) => setBackendHost(e.target.value)}
              placeholder="host.docker.internal"
              autoComplete="off"
              spellCheck={false}
            />
          </label>
          <label className="openwebui-tab__backend-field">
            <span className="openwebui-tab__backend-label">Port</span>
            <input
              type="text"
              className="dashboard-input"
              value={backendPort}
              onChange={(e) => setBackendPort(e.target.value)}
              placeholder="8080"
              autoComplete="off"
              spellCheck={false}
            />
          </label>
        </div>
        {config && !configLoading ? (
          <p className="openwebui-tab__config-hint openwebui-tab__config-hint--muted">
            Effective URL:{' '}
            <code>{config.open_webui_ollama_base_url_effective || config.open_webui_ollama_url_for_container || '—'}</code>
          </p>
        ) : null}
        {backendSaveMsg ? (
          <div
            className={
              backendSaveMsg.startsWith('Saved') || backendSaveMsg.startsWith('Cleared')
                ? 'openwebui-tab__save-ok'
                : 'dashboard-card-error'
            }
            role="status"
          >
            {backendSaveMsg}
          </div>
        ) : null}
      </section>

      <section className="app-default-card" aria-labelledby="openwebui-config-heading">
        <div className="dashboard-card-header">
          <h2 id="openwebui-config-heading">Configuration</h2>
          <div className="dashboard-card-actions">
            <CoreUIButton
              onClick={refreshConfig}
              disabled={configLoading}
            >
              Refresh
            </CoreUIButton>
          </div>
        </div>

        <p className="openwebui-tab__config-hint">
          Other values come from the WebUI server environment (ServiceStarter). Restart the server after changing
          environment variables.
        </p>

        {configErr ? <div className="dashboard-card-error">{configErr}</div> : null}

        {configLoading && !config ? (
          <div className="loading">Loading configuration…</div>
        ) : null}

        {config ? (
          <dl className="openwebui-tab__config-list">
            {CONFIG_LABELS.map(([key, label]) => (
              <React.Fragment key={key}>
                <dt className="openwebui-tab__config-term">
                  {label}
                </dt>
                <dd className="openwebui-tab__config-desc">
                  {config[key] != null && config[key] !== '' ? String(config[key]) : '—'}
                </dd>
              </React.Fragment>
            ))}
          </dl>
        ) : null}
      </section>
    </div>
  );
}

export default OpenWebUiTab;
