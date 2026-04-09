import React, { useCallback, useEffect, useState } from 'react';
import {
  getOpenWebUiStatus,
  getOpenWebUiConfig,
  startOpenWebUi,
  stopOpenWebUi,
} from '../services/api';
import '../styles/components/DashboardTab.css';
import '../styles/components/OpenWebUiTab.css';

const CONFIG_LABELS = [
  ['open_webui_host_url', 'Host URL', 'OPEN_WEBUI_URL'],
  ['open_webui_container_name', 'Container name', 'OPEN_WEBUI_CONTAINER_NAME'],
  ['open_webui_image', 'Docker image', 'OPEN_WEBUI_IMAGE'],
  ['open_webui_host_port', 'Host port', 'OPEN_WEBUI_HOST_PORT'],
  ['open_webui_container_port', 'Container port', 'OPEN_WEBUI_CONTAINER_PORT'],
  ['open_webui_ollama_url_for_container', 'Ollama URL in container', 'OPEN_WEBUI_OLLAMA_BASE_URL'],
];

function OpenWebUiTab({ onErrorStateChange }) {
  const [status, setStatus] = useState(null);
  const [config, setConfig] = useState(null);
  const [configErr, setConfigErr] = useState(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [statusBusy, setStatusBusy] = useState(false);
  const [lastActionOutput, setLastActionOutput] = useState(null);

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

  const running = Boolean(status?.running);
  const url = status?.url || null;
  const statusError = status?.error ? String(status.error) : null;
  const httpErr = status?.http_error ? String(status.http_error) : null;
  const httpStatus =
    status?.http_status != null && status.http_status !== ''
      ? String(status.http_status)
      : null;

  return (
    <div className="dashboard-tab openwebui-tab">
      <div className="claw-proxy-page-header">
        <h2>Open WebUI</h2>
      </div>

      <section className="app-default-card" aria-labelledby="openwebui-status-heading">
        <div className="dashboard-card-header">
          <h2 id="openwebui-status-heading">Service</h2>
          <div className="dashboard-card-actions">
            <button
              type="button"
              className="dashboard-secondary-btn"
              onClick={refreshStatus}
              disabled={statusBusy}
            >
              Refresh
            </button>
            <button
              type="button"
              className="dashboard-primary-btn"
              onClick={handleStartStop}
              disabled={statusBusy}
            >
              {running ? 'Stop service' : 'Start service'}
            </button>
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
          <button
            type="button"
            className="dashboard-secondary-btn"
            onClick={openInBrowser}
            disabled={!running || !url}
          >
            Open in browser
          </button>
        </div>

        {lastActionOutput ? (
          <div className="dashboard-card-error" role="alert">
            {lastActionOutput}
          </div>
        ) : null}
      </section>

      <section className="app-default-card" aria-labelledby="openwebui-config-heading">
        <div className="dashboard-card-header">
          <h2 id="openwebui-config-heading">Configuration</h2>
          <div className="dashboard-card-actions">
            <button
              type="button"
              className="dashboard-secondary-btn"
              onClick={refreshConfig}
              disabled={configLoading}
            >
              Refresh
            </button>
          </div>
        </div>

        <p className="openwebui-tab__config-hint">
          Effective values come from the WebUI server environment (ServiceStarter). Override with env vars
          such as <code>OPEN_WEBUI_URL</code>, <code>OPEN_WEBUI_CONTAINER_NAME</code>,{' '}
          <code>OPEN_WEBUI_IMAGE</code>, <code>OPEN_WEBUI_HOST_PORT</code>,{' '}
          <code>OPEN_WEBUI_CONTAINER_PORT</code>, <code>OPEN_WEBUI_OLLAMA_BASE_URL</code>, then restart the
          server.
        </p>

        {configErr ? <div className="dashboard-card-error">{configErr}</div> : null}

        {configLoading && !config ? (
          <div className="loading">Loading configuration…</div>
        ) : null}

        {config ? (
          <dl className="openwebui-tab__config-list">
            {CONFIG_LABELS.map(([key, label, envHint]) => (
              <React.Fragment key={key}>
                <dt className="openwebui-tab__config-term">
                  {label}
                  <span className="dashboard-rag-status-label" style={{ display: 'block', marginTop: 2 }}>
                    {envHint}
                  </span>
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
