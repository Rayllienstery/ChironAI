import React, { useCallback, useEffect, useState } from 'react';
import {
  getOpenclawStatus,
  getOpenclawTraces,
  clearOpenclawTraces,
  getOpenclawVendorMainSha,
  syncOpenclawVendor,
  rollbackOpenclawVendor,
  getOpenclawVendorVersions,
  getOpenclawSettings,
  updateOpenclawSettings,
} from '../services/api';
import './SettingsTab.css';

function ClawOpenAITab({ onModelStatusChange }) {
  const [status, setStatus] = useState(null);
  const [traces, setTraces] = useState([]);
  const [mainSha, setMainSha] = useState(null);
  const [versions, setVersions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [rollbackSha, setRollbackSha] = useState('');
  const [err, setErr] = useState(null);
  const [availableModels, setAvailableModels] = useState([]);
  const [defaultModel, setDefaultModel] = useState('');

  const refresh = useCallback(async () => {
    setErr(null);
    try {
      const [s, settings] = await Promise.all([getOpenclawStatus(), getOpenclawSettings()]);
      setStatus(s);
      if (s.available) {
        const t = await getOpenclawTraces(50);
        setTraces(t.traces || []);
        const v = await getOpenclawVendorVersions();
        if (v.ok) setVersions(v.versions || []);
      }
      if (settings?.ok) {
        const models = settings.available_models || [];
        const def = settings.default_model || '';
        setAvailableModels(models);
        setDefaultModel(def);
        if (typeof onModelStatusChange === 'function') {
          const inList = Boolean(def && models.some((m) => m.id === def || m.name === def));
          onModelStatusChange(!inList);
        }
      } else if (typeof onModelStatusChange === 'function') {
        onModelStatusChange(true);
      }
    } catch (e) {
      setErr(String(e.message || e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const checkMain = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await getOpenclawVendorMainSha();
      if (r.ok) setMainSha(r.sha);
      else setErr(r.error || 'Could not read main SHA');
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const doSync = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await syncOpenclawVendor();
      if (!r.ok) setErr(r.error || 'Sync failed');
      await refresh();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const doRollback = async () => {
    const sha = rollbackSha.trim().toLowerCase();
    if (sha.length !== 40) {
      setErr('Enter full 40-character commit SHA');
      return;
    }
    setBusy(true);
    setErr(null);
    try {
      const r = await rollbackOpenclawVendor(sha);
      if (!r.ok) setErr(r.error || 'Rollback failed');
      await refresh();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const doClearTraces = async () => {
    try {
      await clearOpenclawTraces();
      await refresh();
    } catch (e) {
      setErr(String(e.message || e));
    }
  };

  if (!status) {
    return (
      <div className="settings-tab">
        <p className="settings-intro">Loading OpenClaw…</p>
      </div>
    );
  }

  if (!status.available) {
    return (
      <div className="settings-tab">
        <h2>Claw OpenAI</h2>
        <p className="settings-intro">
          OpenClaw is not available ({status.reason || 'unknown'}). Install{' '}
          <code>CoreModules/OpenClaw</code> and ensure the app was restarted.
        </p>
      </div>
    );
  }

  return (
    <div className="settings-tab">
      <h2>Claw OpenAI</h2>
      <p className="settings-intro">
        OpenAI-compatible <strong>agent</strong> endpoint with a <code>rag_query</code> tool (ChironAI RAG). Default port{' '}
        <code>8082</code> (see <code>config/openclaw.yaml</code>). Full documentation: repo root{' '}
        <code>Claw.md</code> and <code>docs/OPENCLAW_VSCODE.md</code>.
      </p>
      {err && (
        <p className="settings-intro" style={{ color: 'var(--md-sys-color-error, #b3261e)' }}>
          {err}
        </p>
      )}

      <div className="settings-section">
        <h3>Status</h3>
        <ul className="settings-instructions">
          <li>
            <strong>Enabled</strong>: {String(status.enabled)}
          </li>
          <li>
            <strong>Base URL</strong>: <code>{status.openai_base_url}</code>
          </li>
          <li>
            <strong>Logical model id</strong>: <code>{status.logical_model_id}</code>
          </li>
          <li>
            <strong>Default Ollama model</strong>: <code>{status.default_ollama_model || 'unknown'}</code>
          </li>
          <li>
            <strong>Health</strong>: <code>{status.openai_base_url}/health</code>
          </li>
        </ul>
        <button type="button" className="save-button" onClick={refresh} disabled={busy}>
          Refresh
        </button>
      </div>

      <div className="settings-section">
        <h3>Agent default model</h3>
        <p className="settings-hint">
          This is the <strong>Ollama model</strong> OpenClaw will use when clients request{' '}
          <code>{status.logical_model_id}</code> without overriding <code>model</code>. The list comes from Ollama
          <code> /api/tags</code>.
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center', marginTop: 8 }}>
          <select
            value={defaultModel}
            onChange={(e) => setDefaultModel(e.target.value)}
            style={{ minWidth: 260 }}
          >
            <option value="">Select Ollama model…</option>
            {availableModels.map((m) => (
              <option key={m.id || m.name} value={m.id}>
                {m.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            className="save-button"
            disabled={!defaultModel || busy}
            onClick={async () => {
              try {
                setBusy(true);
                setErr(null);
                await updateOpenclawSettings({ default_model: defaultModel });
                await refresh();
              } catch (e) {
                setErr(String(e.message || e));
              } finally {
                setBusy(false);
              }
            }}
          >
            Save default model
          </button>
        </div>
      </div>

      <div className="settings-section">
        <h3>Vendor (claw-code parity)</h3>
        <p className="settings-hint">
          GitHub: {status.vendor?.github_owner}/{status.vendor?.github_repo} branch {status.vendor?.branch}. Clones into{' '}
          <code>{status.vendor?.root_relative}/versions/&lt;sha&gt;</code> — old versions are kept.
        </p>
        <p>
          <strong>Active</strong>:{' '}
          <code>{status.vendor?.active?.sha || 'none'}</code>
        </p>
        <p>
          <strong>main@GitHub</strong>: {mainSha ? <code>{mainSha}</code> : '—'}
        </p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
          <button type="button" className="save-button" onClick={checkMain} disabled={busy}>
            Check latest main SHA
          </button>
          <button type="button" className="save-button" onClick={doSync} disabled={busy}>
            Update to latest main
          </button>
        </div>
        <p className="settings-hint" style={{ marginTop: 12 }}>
          Installed SHAs: {versions.length ? versions.map((s) => <code key={s}>{s.slice(0, 7)}… </code>) : 'none'}
        </p>
        <div style={{ marginTop: 8, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
          <input
            type="text"
            placeholder="full 40-char sha to activate"
            value={rollbackSha}
            onChange={(e) => setRollbackSha(e.target.value)}
            style={{ minWidth: 280, padding: 8 }}
            aria-label="Rollback SHA"
          />
          <button type="button" className="save-button" onClick={doRollback} disabled={busy}>
            Rollback to SHA
          </button>
        </div>
      </div>

      <div className="settings-section">
        <h3>Traces</h3>
        <p className="settings-hint">
          Last agent runs: model, steps (model_call / rag_query), token estimates, RSS when psutil is installed.
        </p>
        <button type="button" className="save-button" onClick={doClearTraces} style={{ marginBottom: 12 }}>
          Clear trace buffer
        </button>
        <div style={{ maxHeight: 420, overflow: 'auto', fontSize: 13 }}>
          {traces.length === 0 && <p className="settings-hint">No traces yet.</p>}
          {traces.map((t) => (
            <details key={t.trace_id} style={{ marginBottom: 10, borderBottom: '1px solid rgba(128,128,128,0.25)' }}>
              <summary>
                <code>{(t.trace_id || '').slice(0, 8)}</code> · {t.elapsed_ms}ms · {t.step_count} steps ·{' '}
                {t.resolved_model}
                {t.error ? ` · error: ${t.error}` : ''}
              </summary>
              <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{JSON.stringify(t, null, 2)}</pre>
            </details>
          ))}
        </div>
      </div>
    </div>
  );
}

export default ClawOpenAITab;
