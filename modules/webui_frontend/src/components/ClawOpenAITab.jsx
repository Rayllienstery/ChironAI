import React, { useCallback, useEffect, useRef, useState } from 'react';
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
  getRagCollections,
} from '../services/api';
import './DashboardTab.css';

function kvRow(label, value, key) {
  return (
    <div className="dashboard-kv-row" key={key}>
      <span className="dashboard-kv-label">{label}</span>
      <span className="dashboard-kv-value">{value}</span>
    </div>
  );
}

function ClawOpenAITab({ onModelStatusChange }) {
  const onModelStatusChangeRef = useRef(onModelStatusChange);
  onModelStatusChangeRef.current = onModelStatusChange;

  const [status, setStatus] = useState(null);
  const [traces, setTraces] = useState([]);
  const [mainSha, setMainSha] = useState(null);
  const [versions, setVersions] = useState([]);
  const [busy, setBusy] = useState(false);
  const [rollbackSha, setRollbackSha] = useState('');
  const [err, setErr] = useState(null);
  const [availableModels, setAvailableModels] = useState([]);
  const [defaultModel, setDefaultModel] = useState('');
  const [collections, setCollections] = useState([]);
  const [ragCollection, setRagCollection] = useState('');
  const [configDefaultRag, setConfigDefaultRag] = useState('');

  const refresh = useCallback(async () => {
    setErr(null);
    try {
      const [s, settings, colData] = await Promise.all([
        getOpenclawStatus(),
        getOpenclawSettings(),
        getRagCollections().catch(() => ({ collections: [] })),
      ]);
      setStatus(s);
      setCollections(colData.collections || []);
      if (s.available) {
        const t = await getOpenclawTraces(50);
        setTraces(t.traces || []);
        const v = await getOpenclawVendorVersions();
        if (v.ok) setVersions(v.versions || []);
      }
      const notify = onModelStatusChangeRef.current;
      if (settings?.ok) {
        const models = settings.available_models || [];
        const def = settings.default_model || '';
        setAvailableModels(models);
        setDefaultModel(def);
        setRagCollection(settings.stored_rag_collection != null ? settings.stored_rag_collection : '');
        setConfigDefaultRag(settings.config_default_rag_collection || '');
        if (typeof notify === 'function') {
          const inList = Boolean(def && models.some((m) => m.id === def || m.name === def));
          notify(!inList);
        }
      } else if (typeof notify === 'function') {
        notify(true);
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
      <div className="dashboard-tab">
        <div className="dashboard-layout">
          <p className="dashboard-card-muted">Loading OpenClaw…</p>
        </div>
      </div>
    );
  }

  const collectionNames = collections.map((c) => c.name).filter(Boolean);
  const collectionSelectValue =
    collectionNames.length > 0 && collectionNames.includes((ragCollection || '').trim())
      ? ragCollection
      : '';

  if (!status.available) {
    return (
      <div className="dashboard-tab">
        <div className="dashboard-layout">
          <section className="dashboard-card" aria-labelledby="claw-openai-unavailable-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-openai-unavailable-heading">Claw OpenAI</h2>
            </div>
            <p className="dashboard-card-muted">
              OpenClaw is not available ({status.reason || 'unknown'}). Install <code>CoreModules/OpenClaw</code> and
              ensure the app was restarted.
            </p>
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="dashboard-tab">
      <div className="dashboard-layout">
        <section className="dashboard-card" aria-labelledby="claw-openai-heading">
          <div className="dashboard-card-header">
            <h2 id="claw-openai-heading">Claw OpenAI</h2>
          </div>
          <p className="dashboard-card-muted">
            OpenAI-compatible <strong>agent</strong> endpoint with a <code>rag_query</code> tool (ChironAI RAG). Default
            port <code>8082</code> (see <code>config/openclaw.yaml</code>). Full documentation: repo root{' '}
            <code>Claw.md</code> and <code>docs/OPENCLAW_VSCODE.md</code>.
          </p>
          {err && <div className="dashboard-card-error">{err}</div>}
        </section>

        <div className="dashboard-bottom-grid">
          <section className="dashboard-card" aria-labelledby="claw-status-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-status-heading">Status</h2>
              <div className="dashboard-card-actions">
                <button type="button" className="dashboard-primary-btn" onClick={refresh} disabled={busy}>
                  Refresh
                </button>
              </div>
            </div>
            {kvRow('Enabled', String(status.enabled), 'enabled')}
            {kvRow('Base URL', <code>{status.openai_base_url}</code>, 'base')}
            {kvRow('Logical model id', <code>{status.logical_model_id}</code>, 'logical')}
            {kvRow('Default Ollama model', <code>{status.default_ollama_model || 'unknown'}</code>, 'ollama')}
            {kvRow(
              'RAG collection',
              <code>{status.rag_collection || status.config_default_rag_collection || '—'}</code>,
              'ragcoll',
            )}
            {kvRow('Health', <code>{status.openai_base_url}/health</code>, 'health')}
          </section>

          <section className="dashboard-card" aria-labelledby="claw-model-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-model-heading">Agent default model</h2>
            </div>
            <div className="dashboard-proxy-sections">
              <p className="dashboard-card-muted">
                This is the <strong>Ollama model</strong> OpenClaw will use when clients request{' '}
                <code>{status.logical_model_id}</code> without overriding <code>model</code>. The list comes from Ollama
                <code> /api/tags</code>.
              </p>
              <div className="dashboard-card-actions">
                <select
                  className="dashboard-card-field"
                  value={defaultModel}
                  onChange={(e) => setDefaultModel(e.target.value)}
                  aria-label="Ollama model"
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
                  className="dashboard-primary-btn"
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
          </section>

          <section className="dashboard-card" aria-labelledby="claw-rag-collection-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-rag-collection-heading">RAG collection</h2>
            </div>
            <div className="dashboard-proxy-sections">
              <p className="dashboard-card-muted">
                Qdrant collection used for OpenClaw <code>rag_query</code> (same idea as LLM Proxy). Leave as
                &quot;Config default&quot; to use <code>config/server.yaml</code> <code>qdrant.collection_name</code>
                {configDefaultRag ? (
                  <>
                    {' '}
                    (<code>{configDefaultRag}</code>)
                  </>
                ) : null}
                .
              </p>
              <div className="dashboard-card-actions">
                <select
                  className="dashboard-card-field"
                  value={collectionSelectValue || ''}
                  onChange={(e) => setRagCollection(e.target.value)}
                  disabled={collections.length === 0}
                  aria-label="RAG collection for OpenClaw"
                >
                  <option value="">
                    {collections.length === 0
                      ? 'No collections — create one in RAG / Qdrant'
                      : `Config default${configDefaultRag ? ` (${configDefaultRag})` : ''}`}
                  </option>
                  {collections.map((col) => (
                    <option key={col.name} value={col.name}>
                      {col.name}
                      {col.points_count != null ? ` (${col.points_count} vectors)` : ''}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="dashboard-primary-btn"
                  disabled={busy}
                  onClick={async () => {
                    try {
                      setBusy(true);
                      setErr(null);
                      await updateOpenclawSettings({ rag_collection: ragCollection });
                      await refresh();
                    } catch (e) {
                      setErr(String(e.message || e));
                    } finally {
                      setBusy(false);
                    }
                  }}
                >
                  Save RAG collection
                </button>
              </div>
              {(ragCollection || '').trim() &&
                collectionNames.length > 0 &&
                !collectionNames.includes((ragCollection || '').trim()) && (
                  <p className="dashboard-card-muted">
                    Saved: <code>{ragCollection}</code> (not in current Qdrant list)
                  </p>
                )}
            </div>
          </section>

          <section className="dashboard-card" aria-labelledby="claw-vendor-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-vendor-heading">Vendor (claw-code parity)</h2>
            </div>
            <div className="dashboard-proxy-sections">
              <p className="dashboard-card-muted">
                GitHub: {status.vendor?.github_owner}/{status.vendor?.github_repo} branch {status.vendor?.branch}. Clones
                into <code>{status.vendor?.root_relative}/versions/&lt;sha&gt;</code> — old versions are kept.
              </p>
              {kvRow('Active', <code>{status.vendor?.active?.sha || 'none'}</code>, 'active')}
              {kvRow('main@GitHub', mainSha ? <code>{mainSha}</code> : '—', 'main')}
              <div className="dashboard-card-actions">
                <button type="button" className="dashboard-primary-btn" onClick={checkMain} disabled={busy}>
                  Check latest main SHA
                </button>
                <button type="button" className="dashboard-primary-btn" onClick={doSync} disabled={busy}>
                  Update to latest main
                </button>
              </div>
              <p className="dashboard-card-muted">
                Installed SHAs:{' '}
                {versions.length ? versions.map((s) => <code key={s}>{s.slice(0, 7)}… </code>) : 'none'}
              </p>
              <div className="dashboard-card-actions">
                <input
                  type="text"
                  className="dashboard-card-field"
                  placeholder="full 40-char sha to activate"
                  value={rollbackSha}
                  onChange={(e) => setRollbackSha(e.target.value)}
                  aria-label="Rollback SHA"
                />
                <button type="button" className="dashboard-primary-btn" onClick={doRollback} disabled={busy}>
                  Rollback to SHA
                </button>
              </div>
            </div>
          </section>

          <section className="dashboard-card" aria-labelledby="claw-traces-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-traces-heading">Traces</h2>
              <div className="dashboard-card-actions">
                <button type="button" className="dashboard-primary-btn" onClick={doClearTraces}>
                  Clear trace buffer
                </button>
              </div>
            </div>
            <p className="dashboard-card-muted">
              Last agent runs: model, steps (model_call / rag_query), token estimates, RSS when psutil is installed.
            </p>
            <div className="dashboard-card-scroll">
              {traces.length === 0 && <p className="dashboard-card-muted">No traces yet.</p>}
              {traces.map((t) => (
                <details key={t.trace_id} className="dashboard-trace-item">
                  <summary>
                    <code>{(t.trace_id || '').slice(0, 8)}</code> · {t.elapsed_ms}ms · {t.step_count} steps ·{' '}
                    {t.resolved_model}
                    {t.error ? ` · error: ${t.error}` : ''}
                  </summary>
                  <pre>{JSON.stringify(t, null, 2)}</pre>
                </details>
              ))}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default ClawOpenAITab;
