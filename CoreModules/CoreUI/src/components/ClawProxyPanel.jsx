import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  getClawCodeStatus,
  getClawCodeTraces,
  clearClawCodeTraces,
  getClawCodeVendorMainSha,
  syncClawCodeVendor,
  rollbackClawCodeVendorPrevious,
  getClawCodeVendorVersions,
  getClawCodeSettings,
  updateClawCodeSettings,
} from '../services/api';
import '../styles/components/DashboardTab.css';

function kvRow(label, value, key) {
  return (
    <div className="dashboard-kv-row" key={key}>
      <span className="dashboard-kv-label">{label}</span>
      <span className="dashboard-kv-value">{value}</span>
    </div>
  );
}

function ClawProxyPanel({ onNavigateToRag, onModelStatusChange }) {
  const onModelStatusChangeRef = useRef(onModelStatusChange);
  onModelStatusChangeRef.current = onModelStatusChange;

  const [status, setStatus] = useState(null);
  const [traces, setTraces] = useState([]);
  const [mainSha, setMainSha] = useState(null);
  const [versions, setVersions] = useState([]);
  const [canRollback, setCanRollback] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [availableModels, setAvailableModels] = useState([]);
  const [defaultModel, setDefaultModel] = useState('');
  const [maxStepsInput, setMaxStepsInput] = useState('');
  const [effectiveMaxSteps, setEffectiveMaxSteps] = useState(40);
  const [configMaxStepsYaml, setConfigMaxStepsYaml] = useState(40);
  const [tempInput, setTempInput] = useState('');
  const [topPInput, setTopPInput] = useState('');
  const [globalTemp, setGlobalTemp] = useState(null);
  const [globalTopP, setGlobalTopP] = useState(null);
  const [chatThink, setChatThink] = useState(false);
  const [mergeToolsMode, setMergeToolsMode] = useState('inherit');
  const [effectiveMergeTools, setEffectiveMergeTools] = useState(false);
  const [configMergeToolsYaml, setConfigMergeToolsYaml] = useState(false);

  const refresh = useCallback(async () => {
    setErr(null);
    try {
      const s = await getClawCodeStatus();
      setStatus(s);
      let settings = null;
      if (s.available) {
        try {
          settings = await getClawCodeSettings();
        } catch {
          settings = null;
        }
        const t = await getClawCodeTraces(50);
        setTraces(t.traces || []);
        const v = await getClawCodeVendorVersions();
        if (v.ok) {
          setVersions(v.versions || []);
          setCanRollback(Boolean(v.can_rollback));
        } else {
          setVersions([]);
          setCanRollback(false);
        }
      }
      const notify = onModelStatusChangeRef.current;
      if (settings?.ok) {
        const models = settings.available_models || [];
        const def = settings.default_model || '';
        setAvailableModels(models);
        setDefaultModel(def);
        setMaxStepsInput(settings.stored_max_agent_steps != null ? String(settings.stored_max_agent_steps) : '');
        setEffectiveMaxSteps(Number(settings.max_agent_steps) || 40);
        setConfigMaxStepsYaml(Number(settings.config_max_agent_steps_yaml) || 40);
        setTempInput(settings.stored_chat_temperature != null ? String(settings.stored_chat_temperature) : '');
        setTopPInput(settings.stored_chat_top_p != null ? String(settings.stored_chat_top_p) : '');
        setGlobalTemp(settings.global_chat_temperature);
        setGlobalTopP(settings.global_chat_top_p);
        setChatThink(Boolean(settings.chat_think));
        const sm = settings.stored_merge_client_tools;
        if (sm != null && String(sm).trim() !== '') {
          const t = String(sm).trim().toLowerCase();
          setMergeToolsMode(['1', 'true', 'yes', 'on'].includes(t) ? 'on' : 'off');
        } else {
          setMergeToolsMode('inherit');
        }
        setEffectiveMergeTools(Boolean(settings.merge_client_tools));
        setConfigMergeToolsYaml(Boolean(settings.config_merge_client_tools_yaml));
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
      const r = await getClawCodeVendorMainSha();
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
      const r = await syncClawCodeVendor();
      if (!r.ok) setErr(r.error || 'Sync failed');
      await refresh();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const doRollbackPrevious = async () => {
    setBusy(true);
    setErr(null);
    try {
      const r = await rollbackClawCodeVendorPrevious();
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
      await clearClawCodeTraces();
      await refresh();
    } catch (e) {
      setErr(String(e.message || e));
    }
  };

  if (!status) {
    return (
      <div className="dashboard-layout">
        <p className="dashboard-card-muted">Loading ClawCode…</p>
      </div>
    );
  }

  if (!status.available) {
    return (
      <div className="dashboard-layout">
        <section className="app-default-card" aria-labelledby="claw-proxy-unavailable-heading">
          <div className="dashboard-card-header">
            <h2 id="claw-proxy-unavailable-heading">Claw Proxy</h2>
          </div>
          <p className="dashboard-card-muted">
            ClawCode is not available ({status.reason || 'unknown'}). Install <code>CoreModules/ClawCode</code> and
            ensure the app was restarted.
          </p>
        </section>
      </div>
    );
  }

  const saveAgentRuntime = async () => {
    const payload = {};
    if (maxStepsInput.trim() === '') {
      payload.max_agent_steps = null;
    } else {
      const n = parseInt(maxStepsInput, 10);
      if (Number.isNaN(n) || n < 1 || n > 256) {
        setErr('Max agent steps must be an integer 1–256, or empty to use config default');
        return;
      }
      payload.max_agent_steps = n;
    }
    payload.chat_temperature = tempInput.trim() === '' ? null : tempInput.trim();
    payload.chat_top_p = topPInput.trim() === '' ? null : topPInput.trim();
    payload.chat_think = chatThink;
    if (mergeToolsMode === 'inherit') {
      payload.merge_client_tools = null;
    } else {
      payload.merge_client_tools = mergeToolsMode === 'on';
    }
    setBusy(true);
    setErr(null);
    try {
      await updateClawCodeSettings(payload);
      await refresh();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="dashboard-layout">
      <section className="app-default-card" aria-labelledby="claw-proxy-intro-heading">
        <div className="dashboard-card-header">
          <h2 id="claw-proxy-intro-heading">ClawCode HTTP agent</h2>
        </div>
        <p className="dashboard-card-muted">
          <strong>OpenAI</strong> (<code>POST /v1/chat/completions</code>) and <strong>Anthropic</strong> (
          <code>POST /v1/messages</code>) <strong>agent</strong> endpoints share the same loop and{' '}
          <code>rag_query</code> tool (ChironAI RAG). Default port <code>8082</code> (see{' '}
          <code>config/clawcode.yaml</code>). Documentation: <code>Claw.md</code>, <code>docs/CLAWCODE_VSCODE.md</code>.
        </p>
        {err && <div className="dashboard-card-error">{err}</div>}
      </section>

      <div className="dashboard-claw-two-col">
        <div className="dashboard-claw-col">
          <section className="app-default-card" aria-labelledby="claw-status-heading">
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

          <section className="app-default-card" aria-labelledby="claw-rag-hint-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-rag-hint-heading">RAG collection</h2>
            </div>
            <p className="dashboard-card-muted">
              The effective Qdrant collection is listed in <strong>Status</strong> above. To override it for ClawCode{' '}
              <code>rag_query</code> (or clear the override to use the server config default), use{' '}
              <strong>RAG / Qdrant</strong> → <strong>Service bindings</strong>.
            </p>
            {typeof onNavigateToRag === 'function' && (
              <div className="dashboard-card-actions">
                <button type="button" className="dashboard-primary-btn" onClick={onNavigateToRag}>
                  Open RAG / Qdrant
                </button>
              </div>
            )}
          </section>

          <section className="app-default-card" aria-labelledby="claw-traces-heading">
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

        <div className="dashboard-claw-col">
          <section className="app-default-card" aria-labelledby="claw-model-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-model-heading">Agent default model</h2>
            </div>
            <div className="dashboard-proxy-sections">
              <p className="dashboard-card-muted">
                This is the <strong>Ollama model</strong> ClawCode will use when clients request{' '}
                <code>{status.logical_model_id}</code> without overriding <code>model</code>. The list comes from Ollama{' '}
                <code>/api/tags</code>.
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
                      await updateClawCodeSettings({ default_model: defaultModel });
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

          <section className="app-default-card" aria-labelledby="claw-agent-runtime-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-agent-runtime-heading">Agent runtime</h2>
            </div>
            <div className="dashboard-proxy-sections">
              <p className="dashboard-card-muted">
                ClawCode-only overrides. Empty fields fall back to <code>config/models.yaml</code> chat options
                (temperature / top_p) or YAML/env max steps (effective now: <strong>{effectiveMaxSteps}</strong>; YAML
                default: <strong>{configMaxStepsYaml}</strong>).
                {globalTemp != null && globalTopP != null && (
                  <>
                    {' '}
                    Global chat defaults: temperature <code>{String(globalTemp)}</code>, top_p{' '}
                    <code>{String(globalTopP)}</code>.
                  </>
                )}
              </p>
              <div className="dashboard-card-muted" style={{ marginBottom: 12 }}>
                <strong>IDE mode</strong> controls whether ClawCode registers your editor&apos;s tools (VS Code Copilot,
                etc.) alongside <code>rag_query</code>. <strong>On</strong> — the model can call IDE tools; the server
                still runs only <code>rag_query</code> locally and returns other <code>tool_calls</code> to the IDE.{' '}
                <strong>Off</strong> — only <code>rag_query</code> is sent to the model (RAG-only / simple API clients
                without a tool loop). <code>rag_query</code> is always available; this does not disable RAG.
                <br />
                Effective now: <code>{String(effectiveMergeTools)}</code>. Precedence: env{' '}
                <code>CLAWCODE_MERGE_CLIENT_TOOLS</code>, then this WebUI choice, then YAML{' '}
                <code>merge_client_tools</code> (<code>{String(configMergeToolsYaml)}</code> in{' '}
                <code>config/clawcode.yaml</code>).
              </div>
              <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                IDE mode
                <select
                  className="dashboard-card-field"
                  value={mergeToolsMode}
                  onChange={(e) => setMergeToolsMode(e.target.value)}
                  aria-label="ClawCode IDE mode"
                >
                  <option value="inherit">Use YAML default</option>
                  <option value="on">On</option>
                  <option value="off">Off</option>
                </select>
              </label>
              <div className="dashboard-card-actions" style={{ flexWrap: 'wrap' }}>
                <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  Max agent steps (1–256, empty = config)
                  <input
                    type="text"
                    inputMode="numeric"
                    className="dashboard-card-field"
                    value={maxStepsInput}
                    onChange={(e) => setMaxStepsInput(e.target.value)}
                    placeholder={`e.g. ${configMaxStepsYaml}`}
                    aria-label="Max agent steps"
                  />
                </label>
                <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  Temperature (empty = global)
                  <input
                    type="text"
                    className="dashboard-card-field"
                    value={tempInput}
                    onChange={(e) => setTempInput(e.target.value)}
                    placeholder={globalTemp != null ? String(globalTemp) : 'inherit'}
                    aria-label="ClawCode temperature override"
                  />
                </label>
                <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  Top P (empty = global)
                  <input
                    type="text"
                    className="dashboard-card-field"
                    value={topPInput}
                    onChange={(e) => setTopPInput(e.target.value)}
                    placeholder={globalTopP != null ? String(globalTopP) : 'inherit'}
                    aria-label="ClawCode top_p override"
                  />
                </label>
                <label
                  className="dashboard-card-muted"
                  style={{ display: 'flex', alignItems: 'center', gap: 8, alignSelf: 'flex-end' }}
                >
                  <input
                    type="checkbox"
                    checked={chatThink}
                    onChange={(e) => setChatThink(e.target.checked)}
                    aria-label="Request Ollama extended thinking when supported"
                  />
                  Ollama <code>think</code> (if model supports it)
                </label>
                <button
                  type="button"
                  className="dashboard-primary-btn"
                  disabled={busy}
                  onClick={saveAgentRuntime}
                  style={{ alignSelf: 'flex-end' }}
                >
                  Save agent runtime
                </button>
              </div>
            </div>
          </section>

          <section className="app-default-card" aria-labelledby="claw-vendor-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-vendor-heading">Vendor (claw-code parity)</h2>
            </div>
            <div className="dashboard-proxy-sections">
              <p className="dashboard-card-muted">
                GitHub: {status.vendor?.github_owner}/{status.vendor?.github_repo} branch {status.vendor?.branch}. Active
                checkout: <code>{status.vendor?.root_relative}/versions/&lt;sha&gt;</code>. Archived copies:{' '}
                <code>{status.vendor?.root_relative}/backups/&lt;sha&gt;</code>.
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
                <button
                  type="button"
                  className="dashboard-primary-btn"
                  onClick={doRollbackPrevious}
                  disabled={busy || !canRollback}
                  title={canRollback ? undefined : 'Update to a new version first to build history'}
                >
                  Rollback to previous version
                </button>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}

export default ClawProxyPanel;
