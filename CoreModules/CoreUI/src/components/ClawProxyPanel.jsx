import React, { useCallback, useEffect, useState, useMemo } from 'react';
import {
  getClawCodeStatus,
  getClawCodeVendorMainSha,
  syncClawCodeVendor,
  rollbackClawCodeVendorPrevious,
  getClawCodeVendorVersions,
  getClawCodeSkills,
  installClawCodeSkills,
  fetchClawCodeSkillRemoteHeads,
  updateClawCodeSkillsBySource,
  deleteClawCodeSkillsBySource,
  deleteClawCodeSkill,
  enableClawCodeSkill,
  disableClawCodeSkill,
} from '../services/api';
import '../styles/components/DashboardTab.css';

function normSourceRef(ref) {
  if (ref == null || ref === '') return null;
  const t = String(ref).trim();
  return t || null;
}

function skillInstallMeta(sk) {
  const s = sk.source || {};
  if (s.type === 'git' && s.url) {
    const refNorm = normSourceRef(s.ref);
    const subNorm = normSourceRef(s.subdir);
    const groupKey = `git:${s.url.trim()}|${refNorm ?? ''}|${subNorm ?? ''}`;
    return {
      kind: 'git',
      groupKey,
      url: s.url.trim(),
      ref: refNorm,
      subdir: subNorm,
    };
  }
  return { kind: 'other', groupKey: 'other:local', url: null, ref: null, subdir: null };
}

function findRemoteHeadEntry(heads, url, ref) {
  const wantR = normSourceRef(ref);
  return (heads || []).find((h) => {
    const hr = normSourceRef(h.ref);
    return h.url && h.url.trim() === url.trim() && hr === wantR;
  });
}

function kvRow(label, value, key) {
  return (
    <div className="dashboard-kv-row" key={key}>
      <span className="dashboard-kv-label">{label}</span>
      <span className="dashboard-kv-value">{value}</span>
    </div>
  );
}

function ClawProxyPanel() {
  const [status, setStatus] = useState(null);
  const [mainSha, setMainSha] = useState(null);
  const [versions, setVersions] = useState([]);
  const [canRollback, setCanRollback] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState(null);
  const [skills, setSkills] = useState([]);
  const [skillUrl, setSkillUrl] = useState('');
  const [skillRef, setSkillRef] = useState('');
  const [skillSubdir, setSkillSubdir] = useState('');
  const [skillsModalOpen, setSkillsModalOpen] = useState(false);
  const [skillsModalTab, setSkillsModalTab] = useState('sources');
  const [remoteHeads, setRemoteHeads] = useState([]);
  const [remoteHeadsLoading, setRemoteHeadsLoading] = useState(false);
  const [remoteHeadsError, setRemoteHeadsError] = useState(null);

  const skillsStats = useMemo(() => {
    const total = skills.length;
    const enabled = skills.filter((s) => s.enabled).length;
    return { total, enabled, disabled: total - enabled };
  }, [skills]);

  const skillSourceGroups = useMemo(() => {
    const map = new Map();
    for (const sk of skills) {
      const meta = skillInstallMeta(sk);
      if (!map.has(meta.groupKey)) {
        map.set(meta.groupKey, { meta, skills: [] });
      }
      map.get(meta.groupKey).skills.push(sk);
    }
    return Array.from(map.values()).sort((a, b) => {
      if (a.meta.kind !== b.meta.kind) return a.meta.kind === 'git' ? -1 : 1;
      return (a.meta.url || '').localeCompare(b.meta.url || '');
    });
  }, [skills]);

  useEffect(() => {
    if (!skillsModalOpen) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setSkillsModalOpen(false);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [skillsModalOpen]);

  useEffect(() => {
    if (!skillsModalOpen) return undefined;
    setSkillsModalTab('sources');
    let cancelled = false;
    setRemoteHeadsLoading(true);
    setRemoteHeadsError(null);
    (async () => {
      try {
        const data = await fetchClawCodeSkillRemoteHeads();
        if (!cancelled) setRemoteHeads(data.heads || []);
      } catch (e) {
        if (!cancelled) setRemoteHeadsError(String(e.message || e));
      } finally {
        if (!cancelled) setRemoteHeadsLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [skillsModalOpen]);

  const refresh = useCallback(async () => {
    setErr(null);
    try {
      const s = await getClawCodeStatus();
      setStatus(s);
      if (s.available) {
        const v = await getClawCodeVendorVersions();
        if (v.ok) {
          setVersions(v.versions || []);
          setCanRollback(Boolean(v.can_rollback));
        } else {
          setVersions([]);
          setCanRollback(false);
        }
        try {
          const sr = await getClawCodeSkills();
          setSkills(sr.skills || []);
        } catch {
          setSkills([]);
        }
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

  return (
    <div className="dashboard-layout">
      <section className="app-default-card" aria-labelledby="claw-proxy-intro-heading">
        <div className="dashboard-card-header">
          <h2 id="claw-proxy-intro-heading">ClawCode HTTP agent</h2>
        </div>
        <p className="dashboard-card-muted">
          <strong>OpenAI</strong> (<code>POST /v1/chat/completions</code>) and <strong>Anthropic</strong> (
          <code>POST /v1/messages</code>) <strong>agent</strong> endpoints share the same loop and{' '}
          <code>rag_query</code> tool (ChironAI RAG). Pass an Ollama model tag in <code>model</code>, or rely on the
          global chat model from RAG config. For LLM Proxy clients, use a build with <code>backend: claw</code>{' '}
          (model/runtime on the build). Default port <code>8082</code> (<code>config/clawcode.yaml</code>). Docs:{' '}
          <code>Claw.md</code>, <code>docs/CLAWCODE_VSCODE.md</code>.
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
            {kvRow('Health', <code>{status.openai_base_url}/health</code>, 'health')}
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
                  <div
                    className="dashboard-claw-skills-modal-tabs"
                    role="tablist"
                    aria-label="Skills manager sections"
                  >
                    <button
                      type="button"
                      role="tab"
                      id="claw-skills-tab-sources"
                      className={
                        skillsModalTab === 'sources'
                          ? 'dashboard-claw-skills-modal-tab dashboard-claw-skills-modal-tab--active'
                          : 'dashboard-claw-skills-modal-tab'
                      }
                      aria-selected={skillsModalTab === 'sources'}
                      aria-controls="claw-skills-panel-sources"
                      onClick={() => setSkillsModalTab('sources')}
                    >
                      By source
                    </button>
                    <button
                      type="button"
                      role="tab"
                      id="claw-skills-tab-per-skill"
                      className={
                        skillsModalTab === 'skills'
                          ? 'dashboard-claw-skills-modal-tab dashboard-claw-skills-modal-tab--active'
                          : 'dashboard-claw-skills-modal-tab'
                      }
                      aria-selected={skillsModalTab === 'skills'}
                      aria-controls="claw-skills-panel-skills"
                      onClick={() => setSkillsModalTab('skills')}
                    >
                      Per skill
                    </button>
                  </div>
                  <div className="dashboard-claw-skills-modal-body">
                    {skillsModalTab === 'sources' ? (
                      <div
                        id="claw-skills-panel-sources"
                        role="tabpanel"
                        aria-labelledby="claw-skills-tab-sources"
                      >
                        <p className="dashboard-card-muted" style={{ marginTop: 0, marginBottom: 12 }}>
                          Git sources are grouped here. Compare installed commit SHA with the latest remote ref (fetched
                          when this dialog opens). Use bulk actions to update, enable, disable, or remove every pack from
                          the same install.
                        </p>
                        {remoteHeadsLoading ? (
                          <p className="dashboard-card-muted">Checking remote heads…</p>
                        ) : null}
                        {remoteHeadsError ? (
                          <p className="dashboard-card-error" style={{ marginBottom: 12 }}>
                            {remoteHeadsError}
                          </p>
                        ) : null}
                        <div className="dashboard-claw-skills-modal-source-groups">
                          {skillSourceGroups.map(({ meta, skills: groupSkills }) => {
                            const shas = [
                              ...new Set(groupSkills.map((s) => s.source_commit_sha).filter(Boolean)),
                            ];
                            const installedLabel =
                              shas.length === 0 ? '—' : shas.length === 1 ? `${shas[0].slice(0, 7)}…` : 'Mixed';
                            const remoteEntry =
                              meta.kind === 'git'
                                ? findRemoteHeadEntry(remoteHeads, meta.url, meta.ref)
                                : null;
                            const remoteSha = remoteEntry?.remote_sha;
                            const remoteErr = remoteEntry?.error;
                            const updateAvailable =
                              meta.kind === 'git' &&
                              Boolean(remoteSha) &&
                              !remoteErr &&
                              shas.length === 1 &&
                              shas[0] !== remoteSha;
                            const names = groupSkills
                              .map((s) => s.invocation_name || s.display_name || s.id)
                              .join(', ');
                            const allEnabled = groupSkills.every((s) => s.enabled);
                            const allDisabled = groupSkills.every((s) => !s.enabled);
                            const payload = {
                              url: meta.url,
                              ref: meta.ref || undefined,
                              subdir: meta.subdir || undefined,
                            };
                            return (
                              <div key={meta.groupKey} className="dashboard-claw-skills-modal-source-group">
                                <div className="dashboard-claw-skills-modal-source-group-head">
                                  <div>
                                    {meta.kind === 'git' ? (
                                      <>
                                        <code className="dashboard-claw-skills-modal-source-group-url">
                                          {meta.url}
                                        </code>
                                        <p className="dashboard-claw-skills-modal-source-group-meta">
                                          {meta.ref ? (
                                            <>
                                              ref <code>{meta.ref}</code>
                                              {' · '}
                                            </>
                                          ) : (
                                            <>default branch · </>
                                          )}
                                          {meta.subdir ? (
                                            <>
                                              subdir <code>{meta.subdir}</code>
                                              {' · '}
                                            </>
                                          ) : null}
                                          {groupSkills.length} pack{groupSkills.length === 1 ? '' : 's'}
                                        </p>
                                        <p className="dashboard-claw-skills-modal-sha-row">
                                          <span>
                                            Installed: <code>{installedLabel}</code>
                                          </span>
                                          {remoteSha ? (
                                            <span>
                                              Remote: <code>{remoteSha.slice(0, 7)}…</code>
                                            </span>
                                          ) : remoteErr ? (
                                            <span className="dashboard-card-muted">Remote: error</span>
                                          ) : (
                                            <span className="dashboard-card-muted">Remote: —</span>
                                          )}
                                          {updateAvailable ? (
                                            <span
                                              className="dashboard-claw-skills-modal-update-badge"
                                              title="Installed commit differs from fetched remote HEAD"
                                            >
                                              Update available
                                            </span>
                                          ) : null}
                                        </p>
                                        {remoteErr ? (
                                          <p className="dashboard-card-muted" style={{ marginTop: 6, fontSize: '0.8rem' }}>
                                            {remoteErr}
                                          </p>
                                        ) : null}
                                      </>
                                    ) : (
                                      <>
                                        <strong>Non-Git sources</strong>
                                        <p className="dashboard-card-muted" style={{ marginTop: 6 }}>
                                          No Git remote to compare or bulk-update. Enable or disable packs below; remove
                                          all uninstalls every pack in this group.
                                        </p>
                                      </>
                                    )}
                                    <p className="dashboard-claw-skills-modal-source-group-names" title={names}>
                                      {names}
                                    </p>
                                  </div>
                                </div>
                                <div className="dashboard-card-actions dashboard-claw-skills-modal-source-group-actions">
                                  {meta.kind === 'git' ? (
                                    <>
                                      <button
                                        type="button"
                                        className="dashboard-primary-btn"
                                        disabled={busy}
                                        onClick={async () => {
                                          setBusy(true);
                                          setErr(null);
                                          try {
                                            await updateClawCodeSkillsBySource(payload);
                                            await refresh();
                                            try {
                                              const data = await fetchClawCodeSkillRemoteHeads();
                                              setRemoteHeads(data.heads || []);
                                            } catch {
                                              /* ignore */
                                            }
                                          } catch (e) {
                                            setErr(String(e.message || e));
                                          } finally {
                                            setBusy(false);
                                          }
                                        }}
                                      >
                                        Update all
                                      </button>
                                      <button
                                        type="button"
                                        className="dashboard-secondary-btn"
                                        disabled={busy || allEnabled}
                                        onClick={async () => {
                                          setBusy(true);
                                          setErr(null);
                                          try {
                                            for (const s of groupSkills) {
                                              if (!s.enabled) await enableClawCodeSkill(s.id);
                                            }
                                            await refresh();
                                          } catch (e) {
                                            setErr(String(e.message || e));
                                          } finally {
                                            setBusy(false);
                                          }
                                        }}
                                      >
                                        Enable all
                                      </button>
                                      <button
                                        type="button"
                                        className="dashboard-secondary-btn"
                                        disabled={busy || allDisabled}
                                        onClick={async () => {
                                          setBusy(true);
                                          setErr(null);
                                          try {
                                            for (const s of groupSkills) {
                                              if (s.enabled) await disableClawCodeSkill(s.id);
                                            }
                                            await refresh();
                                          } catch (e) {
                                            setErr(String(e.message || e));
                                          } finally {
                                            setBusy(false);
                                          }
                                        }}
                                      >
                                        Disable all
                                      </button>
                                      <button
                                        type="button"
                                        className="dashboard-secondary-btn"
                                        disabled={busy}
                                        onClick={async () => {
                                          if (
                                            !window.confirm(
                                              `Remove all ${groupSkills.length} skill pack(s) from this Git source?`
                                            )
                                          )
                                            return;
                                          setBusy(true);
                                          setErr(null);
                                          try {
                                            await deleteClawCodeSkillsBySource(payload);
                                            await refresh();
                                            const sr = await getClawCodeSkills().catch(() => ({ skills: [] }));
                                            if (!(sr.skills || []).length) setSkillsModalOpen(false);
                                          } catch (e) {
                                            setErr(String(e.message || e));
                                          } finally {
                                            setBusy(false);
                                          }
                                        }}
                                      >
                                        Remove all
                                      </button>
                                    </>
                                  ) : (
                                    <>
                                      <button
                                        type="button"
                                        className="dashboard-secondary-btn"
                                        disabled={busy || allEnabled}
                                        onClick={async () => {
                                          setBusy(true);
                                          setErr(null);
                                          try {
                                            for (const s of groupSkills) {
                                              if (!s.enabled) await enableClawCodeSkill(s.id);
                                            }
                                            await refresh();
                                          } catch (e) {
                                            setErr(String(e.message || e));
                                          } finally {
                                            setBusy(false);
                                          }
                                        }}
                                      >
                                        Enable all
                                      </button>
                                      <button
                                        type="button"
                                        className="dashboard-secondary-btn"
                                        disabled={busy || allDisabled}
                                        onClick={async () => {
                                          setBusy(true);
                                          setErr(null);
                                          try {
                                            for (const s of groupSkills) {
                                              if (s.enabled) await disableClawCodeSkill(s.id);
                                            }
                                            await refresh();
                                          } catch (e) {
                                            setErr(String(e.message || e));
                                          } finally {
                                            setBusy(false);
                                          }
                                        }}
                                      >
                                        Disable all
                                      </button>
                                      <button
                                        type="button"
                                        className="dashboard-secondary-btn"
                                        disabled={busy}
                                        onClick={async () => {
                                          if (
                                            !window.confirm(
                                              `Remove all ${groupSkills.length} non-Git skill pack(s) from this server?`
                                            )
                                          )
                                            return;
                                          setBusy(true);
                                          setErr(null);
                                          try {
                                            for (const s of groupSkills) {
                                              await deleteClawCodeSkill(s.id);
                                            }
                                            await refresh();
                                            const sr = await getClawCodeSkills().catch(() => ({ skills: [] }));
                                            if (!(sr.skills || []).length) setSkillsModalOpen(false);
                                          } catch (e) {
                                            setErr(String(e.message || e));
                                          } finally {
                                            setBusy(false);
                                          }
                                        }}
                                      >
                                        Remove all
                                      </button>
                                    </>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : (
                      <div
                        id="claw-skills-panel-skills"
                        role="tabpanel"
                        aria-labelledby="claw-skills-tab-per-skill"
                      >
                        <p className="dashboard-card-muted" style={{ marginTop: 0, marginBottom: 14 }}>
                          Turn packs on or off for the agent. Updates and removal by Git source are on the{' '}
                          <strong>By source</strong> tab.
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
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            ) : null}
          </section>
        </div>

        <div className="dashboard-claw-col">
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
