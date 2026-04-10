import React, { useCallback, useEffect, useRef, useState, useMemo } from 'react';
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
  getClawCodeSkills,
  installClawCodeSkills,
  updateClawCodeSkill,
  deleteClawCodeSkill,
  enableClawCodeSkill,
  disableClawCodeSkill,
} from '../services/api';
import '../styles/components/DashboardTab.css';
import { summarizeClawTraceMeta } from '../utils/clawTraceSummary';
import ClawTraceSummaryCards from './ClawTraceSummaryCards';

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
  const [skills, setSkills] = useState([]);
  const [skillUrl, setSkillUrl] = useState('');
  const [skillRef, setSkillRef] = useState('');
  const [skillSubdir, setSkillSubdir] = useState('');
  const [skillsModalOpen, setSkillsModalOpen] = useState(false);

  const skillsStats = useMemo(() => {
    const total = skills.length;
    const enabled = skills.filter((s) => s.enabled).length;
    return { total, enabled, disabled: total - enabled };
  }, [skills]);

  useEffect(() => {
    if (!skillsModalOpen) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setSkillsModalOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [skillsModalOpen]);

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
        try {
          const sr = await getClawCodeSkills();
          setSkills(sr.skills || []);
        } catch {
          setSkills([]);
        }
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
                  <ClawTraceSummaryCards summary={summarizeClawTraceMeta(t)} />
                  <details className="dashboard-trace-item" style={{ marginTop: 12 }}>
                    <summary>Full JSON</summary>
                    <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{JSON.stringify(t, null, 2)}</pre>
                  </details>
                </details>
              ))}
            </div>
          </section>

          <section className="app-default-card" aria-labelledby="claw-skills-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-skills-heading">Skills</h2>
              <div className="dashboard-card-actions">
                <button type="button" className="dashboard-primary-btn" onClick={refresh} disabled={busy}>
                  Refresh
                </button>
              </div>
            </div>

            <div className="dashboard-claw-skills-summary">
              <h3 className="dashboard-claw-skills-summary-title">ClawCode skill packs</h3>
              <p className="dashboard-claw-skills-summary-text">
                Skills are instruction packs (folders with <code>SKILL.md</code>) installed from Git. ClawCode injects
                enabled packs into the agent prompt for <strong>every</strong> Ollama model. Disabled packs stay on disk
                but are skipped until you enable them again.
              </p>
              <ul className="dashboard-claw-skills-summary-stats" aria-live="polite">
                <li>
                  <strong>{skillsStats.total}</strong> installed
                </li>
                <li>
                  <strong>{skillsStats.enabled}</strong> enabled
                </li>
                {skillsStats.disabled > 0 ? (
                  <li className="dashboard-claw-skills-summary-stats--muted">
                    <strong>{skillsStats.disabled}</strong> disabled
                  </li>
                ) : null}
              </ul>
              <div className="dashboard-claw-skills-summary-actions">
                <button
                  type="button"
                  className="dashboard-primary-btn"
                  onClick={() => setSkillsModalOpen(true)}
                  disabled={busy || skills.length === 0}
                  aria-haspopup="dialog"
                  aria-expanded={skillsModalOpen}
                  aria-controls="claw-skills-list-dialog"
                >
                  {skills.length === 0 ? 'No skills to manage' : `Manage installed skills (${skills.length})`}
                </button>
              </div>
            </div>

            <div className="dashboard-card-actions" style={{ gap: 8, flexWrap: 'wrap', marginTop: 16 }}>
              <input
                className="dashboard-input"
                style={{ minWidth: 320 }}
                value={skillUrl}
                onChange={(e) => setSkillUrl(e.target.value)}
                placeholder="Git repo URL (e.g. https://github.com/anthropics/skills)"
                aria-label="Skill repo URL"
              />
              <input
                className="dashboard-input"
                style={{ width: 160 }}
                value={skillRef}
                onChange={(e) => setSkillRef(e.target.value)}
                placeholder="ref (optional)"
                aria-label="Skill repo ref"
              />
              <input
                className="dashboard-input"
                style={{ width: 220 }}
                value={skillSubdir}
                onChange={(e) => setSkillSubdir(e.target.value)}
                placeholder="subdir (optional)"
                aria-label="Skill repo subdir"
              />
              <button
                type="button"
                className="dashboard-primary-btn"
                disabled={busy || !skillUrl.trim()}
                onClick={async () => {
                  setBusy(true);
                  setErr(null);
                  try {
                    await installClawCodeSkills({
                      url: skillUrl.trim(),
                      ref: skillRef.trim() || undefined,
                      subdir: skillSubdir.trim() || undefined,
                    });
                    setSkillUrl('');
                    setSkillRef('');
                    setSkillSubdir('');
                    await refresh();
                  } catch (e) {
                    setErr(String(e.message || e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Install
              </button>
            </div>

            {!skills.length ? (
              <p className="dashboard-card-muted" style={{ marginTop: 12 }}>
                No skills installed yet. Add a Git URL above, then open <strong>Manage installed skills</strong> when the
                list is non-empty.
              </p>
            ) : null}

            {skillsModalOpen ? (
              <div
                className="dashboard-claw-skills-modal-overlay"
                role="presentation"
                onClick={() => setSkillsModalOpen(false)}
              >
                <div
                  id="claw-skills-list-dialog"
                  className="dashboard-claw-skills-modal"
                  role="dialog"
                  aria-modal="true"
                  aria-labelledby="claw-skills-modal-title"
                  onClick={(e) => e.stopPropagation()}
                >
                  <div className="dashboard-claw-skills-modal-header">
                    <h3 id="claw-skills-modal-title">Installed skills</h3>
                    <button
                      type="button"
                      className="dashboard-claw-skills-modal-close"
                      onClick={() => setSkillsModalOpen(false)}
                      aria-label="Close"
                    >
                      Close
                    </button>
                  </div>
                  <div className="dashboard-claw-skills-modal-body">
                    <p className="dashboard-card-muted" style={{ marginTop: 0, marginBottom: 14 }}>
                      Enable or disable globally, pull updates from Git, or remove a pack from this server.
                    </p>
                    <div className="dashboard-claw-skills-modal-list">
                      {skills.map((sk) => {
                        const sid = sk.id;
                        const enabled = Boolean(sk.enabled);
                        return (
                          <div key={sid} className="dashboard-claw-skills-modal-item">
                            <div className="dashboard-claw-skills-modal-item-head">
                              <strong>{sk.invocation_name || sk.display_name || sid}</strong>
                              {enabled ? (
                                <span className="dashboard-claw-skills-modal-badge dashboard-claw-skills-modal-badge--on">
                                  On
                                </span>
                              ) : (
                                <span className="dashboard-claw-skills-modal-badge">Off</span>
                              )}
                            </div>
                            <code className="dashboard-claw-skills-modal-id">{sid}</code>
                            {sk.description ? (
                              <p className="dashboard-claw-skills-modal-desc">{sk.description}</p>
                            ) : (
                              <p className="dashboard-card-muted dashboard-claw-skills-modal-desc">No description</p>
                            )}
                            <p className="dashboard-card-muted dashboard-claw-skills-modal-source">
                              {sk.source?.type === 'git' && sk.source?.url ? (
                                <>
                                  Source: <code>{sk.source.url}</code>
                                  {sk.source.ref ? (
                                    <>
                                      {' '}
                                      @ <code>{sk.source.ref}</code>
                                    </>
                                  ) : null}
                                  {sk.source.repo_rel_skill_dir ? (
                                    <>
                                      {' '}
                                      · <code>{sk.source.repo_rel_skill_dir}</code>
                                    </>
                                  ) : null}
                                </>
                              ) : (
                                <>
                                  Source: <code>{sk.source?.type || 'unknown'}</code>
                                </>
                              )}
                            </p>
                            <div className="dashboard-card-actions" style={{ gap: 8, flexWrap: 'wrap' }}>
                              <button
                                type="button"
                                className="dashboard-primary-btn"
                                disabled={busy}
                                onClick={async () => {
                                  setBusy(true);
                                  setErr(null);
                                  try {
                                    if (enabled) {
                                      await disableClawCodeSkill(sid);
                                    } else {
                                      await enableClawCodeSkill(sid);
                                    }
                                    await refresh();
                                  } catch (e) {
                                    setErr(String(e.message || e));
                                  } finally {
                                    setBusy(false);
                                  }
                                }}
                              >
                                {enabled ? 'Disable' : 'Enable'}
                              </button>
                              <button
                                type="button"
                                className="dashboard-secondary-btn"
                                disabled={busy}
                                onClick={async () => {
                                  setBusy(true);
                                  setErr(null);
                                  try {
                                    await updateClawCodeSkill(sid);
                                    await refresh();
                                  } catch (e) {
                                    setErr(String(e.message || e));
                                  } finally {
                                    setBusy(false);
                                  }
                                }}
                              >
                                Update
                              </button>
                              <button
                                type="button"
                                className="dashboard-secondary-btn"
                                disabled={busy}
                                onClick={async () => {
                                  if (!window.confirm(`Delete skill ${sk.invocation_name || sid}?`)) return;
                                  setBusy(true);
                                  setErr(null);
                                  try {
                                    await deleteClawCodeSkill(sid);
                                    await refresh();
                                    if (skills.length <= 1) setSkillsModalOpen(false);
                                  } catch (e) {
                                    setErr(String(e.message || e));
                                  } finally {
                                    setBusy(false);
                                  }
                                }}
                              >
                                Remove
                              </button>
                            </div>
                          </div>
                        );
                      })}
                    </div>
                  </div>
                </div>
              </div>
            ) : null}
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
              <p className="dashboard-card-muted" style={{ marginBottom: 12 }}>
                <strong>IDE mode</strong> (<code>merge_client_tools</code>) is configured under{' '}
                <strong>Settings</strong> → ClawCode.
              </p>
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
