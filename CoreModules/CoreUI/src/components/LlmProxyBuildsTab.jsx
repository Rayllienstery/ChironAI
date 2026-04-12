import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  getLlmProxyBuilds,
  putLlmProxyBuilds,
  getModels,
  getPrompts,
  previewLlmProxyBuildModel,
  getModelSettings,
  getPipelinePreview,
  getRagModelSettings,
  getClawCodeSkills,
} from '../services/api';
import { mergePipelineSnapshot } from '../hooks/useMergedPipelinePreview';
import PipelineCiDiagram from './PipelineCiDiagram';
import LlmProxyAutocompletePanel from './LlmProxyAutocompletePanel';
import '../styles/components/DashboardTab.css';
import '../styles/components/SettingsTab.css';
import '../styles/components/CoreUIPillTabs.css';
import '../styles/components/LlmProxyTab.css';

const SECTION_TABS = [
  { id: 'builds', label: 'Builds' },
  { id: 'autocomplete', label: 'Autocomplete' },
];

const DEFAULT_CLAW_STEPS = 40;

function mergeBuildDraftIntoPipelinePreview(snapshot, hybridSparse, rerankForRag, draft, clawSkillsToolAvailable) {
  if (!snapshot || !draft) return null;
  const base = mergePipelineSnapshot(snapshot, hybridSparse, rerankForRag);
  const webOff = draft.web_enabled === false;
  const env = base.env && typeof base.env === 'object' ? { ...base.env } : {};
  if (webOff) {
    env.ddg_news = false;
    env.fetch_page = false;
    env.wikipedia = false;
  } else {
    env.ddg_news = Boolean(draft.web_interaction_ddg_news) || Boolean(env.ddg_news);
    env.fetch_page = Boolean(draft.web_interaction_fetch_page) || Boolean(env.fetch_page);
    env.wikipedia = Boolean(draft.web_interaction_wikipedia) || Boolean(env.wikipedia);
  }
  return {
    ...base,
    env,
    claw_build_pipeline_preview: true,
    backend: String(draft.backend || 'dumb').toLowerCase(),
    skills_enabled: draft.skills_enabled !== false,
    claw_skills_tool_available: clawSkillsToolAvailable,
    rag_collection_configured:
      Boolean(draft.rag_enabled) &&
      (Boolean(String(draft.rag_collection || '').trim()) || Boolean(base.rag_collection_configured)),
    fetch_web_knowledge: webOff ? false : Boolean(draft.fetch_web_knowledge),
    web_interaction_enabled: webOff ? false : Boolean(draft.web_interaction_enabled),
    web_interaction_on_keywords: draft.web_interaction_on_keywords !== false,
    web_interaction_on_low_confidence_framework:
      draft.web_interaction_on_low_confidence_framework !== false,
  };
}

function CoreUiModal({ title, onClose, children }) {
  const panelRef = useRef(null);

  useEffect(() => {
    const prev = document.activeElement;
    const t = setTimeout(() => {
      try {
        panelRef.current?.querySelector?.('input,select,button,textarea,[tabindex]')?.focus?.();
      } catch {
        /* ignore */
      }
    }, 0);
    return () => {
      clearTimeout(t);
      try {
        prev?.focus?.();
      } catch {
        /* ignore */
      }
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div
      className="coreui-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
    >
      <div className="coreui-modal" ref={panelRef}>
        <div className="coreui-modal-header">
          <h3>{title}</h3>
          <button type="button" className="coreui-modal-close-btn" onClick={onClose} aria-label="Close dialog">
            Close
          </button>
        </div>
        <div className="coreui-modal-body">{children}</div>
      </div>
    </div>
  );
}

function emptyDraft() {
  return {
    id: '',
    display_name: '',
    backend: 'dumb',
    ollama_model: '',
    prompt_name: '',
    rag_enabled: true,
    skills_enabled: true,
    web_enabled: true,
    fetch_web_knowledge: false,
    web_interaction_enabled: false,
    web_interaction_on_keywords: true,
    web_interaction_on_low_confidence_framework: true,
    web_interaction_ddg_news: false,
    web_interaction_fetch_page: false,
    web_interaction_wikipedia: false,
    code_only: false,
    include_rag_metadata: true,
    reasoning_level: '',
    chat_think: false,
    private: false,
    rag_collection: '',
    context_chunk_chars: '',
    context_total_chars: '',
    rag_top_k: '',
    temperature: '',
    top_p: '',
    max_agent_steps: '',
    num_ctx: '',
  };
}

function buildToDraft(b) {
  if (!b) return emptyDraft();
  const d = emptyDraft();
  Object.keys(d).forEach((k) => {
    if (b[k] !== undefined && b[k] !== null) {
      if (typeof b[k] === 'boolean') d[k] = b[k];
      else d[k] = String(b[k]);
    }
  });
  if (b.backend) d.backend = String(b.backend);
  return d;
}

function draftToPayload(draft) {
  const o = { ...draft };
  o.id = String(draft.id || '').trim();
  o.display_name = String(draft.display_name || '').trim() || o.id;
  o.backend = String(draft.backend || 'dumb').toLowerCase();
  o.ollama_model = String(draft.ollama_model || '').trim();
  o.prompt_name = String(draft.prompt_name || '').trim();
  o.rag_enabled = Boolean(draft.rag_enabled);
  o.skills_enabled = Boolean(draft.skills_enabled);
  o.web_enabled = Boolean(draft.web_enabled);
  o.fetch_web_knowledge = Boolean(draft.fetch_web_knowledge);
  o.web_interaction_enabled = Boolean(draft.web_interaction_enabled);
  o.web_interaction_on_keywords = draft.web_interaction_on_keywords !== false;
  o.web_interaction_on_low_confidence_framework =
    draft.web_interaction_on_low_confidence_framework !== false;
  o.web_interaction_ddg_news = Boolean(draft.web_interaction_ddg_news);
  o.web_interaction_fetch_page = Boolean(draft.web_interaction_fetch_page);
  o.web_interaction_wikipedia = Boolean(draft.web_interaction_wikipedia);
  o.code_only = Boolean(draft.code_only);
  o.include_rag_metadata = Boolean(draft.include_rag_metadata);
  o.chat_think = Boolean(draft.chat_think);
  o.private = Boolean(draft.private);
  o.reasoning_level = String(draft.reasoning_level || '').trim();
  o.rag_collection = String(draft.rag_collection || '').trim();
  [
    'temperature',
    'top_p',
    'max_agent_steps',
    'num_ctx',
    'context_chunk_chars',
    'context_total_chars',
    'rag_top_k',
  ].forEach((k) => {
    const s = String(draft[k] ?? '').trim();
    if (s === '') delete o[k];
    else if (
      k === 'max_agent_steps' ||
      k === 'num_ctx' ||
      k === 'context_chunk_chars' ||
      k === 'context_total_chars' ||
      k === 'rag_top_k'
    )
      o[k] = parseInt(s, 10);
    else o[k] = parseFloat(s);
  });
  return o;
}

function LlmProxyBuildsTab({ focusSubTab, onFocusSubTabConsumed }) {
  const [sectionTab, setSectionTab] = useState('builds');
  const [builds, setBuilds] = useState([]);
  const [urls, setUrls] = useState({ main: '', build_proxy: '' });
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);
  const [models, setModels] = useState([]);
  const [prompts, setPrompts] = useState([]);
  const [proxyDefaults, setProxyDefaults] = useState(null);
  const [draft, setDraft] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewMsg, setPreviewMsg] = useState(null);
  const [buildModalPipelineSnap, setBuildModalPipelineSnap] = useState(null);
  const [buildModalHybrid, setBuildModalHybrid] = useState(true);
  const [buildModalRerank, setBuildModalRerank] = useState(false);
  const [buildModalClawSkillsAvail, setBuildModalClawSkillsAvail] = useState(false);

  const load = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const [b, m, p, ms] = await Promise.all([
        getLlmProxyBuilds(),
        getModels(),
        getPrompts(),
        getModelSettings(),
      ]);
      setBuilds(b.builds || []);
      setUrls(b.openai_models_urls || {});
      setModels(Array.isArray(m) ? m : []);
      setPrompts(p.prompts || []);
      setProxyDefaults(ms || null);
    } catch (e) {
      setErr(String(e.message || e));
      setBuilds([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (focusSubTab !== 'autocomplete') return;
    setSectionTab('autocomplete');
    if (typeof onFocusSubTabConsumed === 'function') {
      onFocusSubTabConsumed();
    }
  }, [focusSubTab, onFocusSubTabConsumed]);

  const buildModalOpen = Boolean(draft);
  const buildModalBackendKey = draft ? String(draft.backend || '').toLowerCase() : '';

  useEffect(() => {
    if (!draft) {
      setBuildModalPipelineSnap(null);
      setBuildModalClawSkillsAvail(false);
      return undefined;
    }
    let cancelled = false;
    const backendLower = String(draft.backend || '').toLowerCase();
    (async () => {
      try {
        const [p, r] = await Promise.all([getPipelinePreview(), getRagModelSettings()]);
        if (cancelled) return;
        setBuildModalPipelineSnap(p);
        setBuildModalHybrid(r?.hybrid_sparse_enabled !== false);
        setBuildModalRerank(Boolean(r?.rerank_for_rag));
        let clawOk = false;
        if (backendLower === 'claw') {
          try {
            const sk = await getClawCodeSkills();
            const list = sk?.skills || [];
            clawOk = Array.isArray(list) && list.some((s) => s.enabled);
          } catch {
            clawOk = false;
          }
        }
        if (!cancelled) setBuildModalClawSkillsAvail(clawOk);
      } catch {
        if (!cancelled) setBuildModalPipelineSnap(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // Intentionally omit `draft` so typing other fields does not refetch; open + backend drive reload.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- draft read from latest render when deps change
  }, [buildModalOpen, buildModalBackendKey]);

  const buildModalPipelineData = useMemo(
    () =>
      mergeBuildDraftIntoPipelinePreview(
        buildModalPipelineSnap,
        buildModalHybrid,
        buildModalRerank,
        draft,
        buildModalClawSkillsAvail,
      ),
    [buildModalPipelineSnap, buildModalHybrid, buildModalRerank, draft, buildModalClawSkillsAvail],
  );

  const detailBuild = useMemo(
    () => builds.find((x) => x.id === detailId) || null,
    [builds, detailId],
  );

  const openNew = () => {
    setDetailId(null);
    setEditingId(null);
    setDraft(emptyDraft());
    setPreviewMsg(null);
  };

  const openEdit = (b) => {
    setDetailId(null);
    setEditingId(b.id);
    setDraft(buildToDraft(b));
    setPreviewMsg(null);
  };

  const openDetails = (bid) => {
    setDraft(null);
    setEditingId(null);
    setPreviewMsg(null);
    setDetailId(bid);
  };

  const closeForm = () => {
    setDraft(null);
    setEditingId(null);
    setPreviewMsg(null);
  };

  const closeDetails = () => {
    setDetailId(null);
  };

  const saveForm = async () => {
    if (!draft) return;
    const payload = draftToPayload(draft);
    let next = builds.map((x) => ({ ...x }));
    if (editingId) {
      const i = next.findIndex((x) => x.id === editingId);
      if (i >= 0) next[i] = { ...next[i], ...payload };
      else next.push(payload);
    } else {
      if (next.some((x) => x.id === payload.id)) {
        setErr(`Build id "${payload.id}" already exists.`);
        return;
      }
      next.push(payload);
    }
    setSaving(true);
    setErr(null);
    try {
      const data = await putLlmProxyBuilds(next);
      setBuilds(data.builds || next);
      closeForm();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setSaving(false);
    }
  };

  const deleteBuild = async (bid) => {
    if (!window.confirm(`Delete build "${bid}"?`)) return;
    const next = builds.filter((x) => x.id !== bid);
    setSaving(true);
    setErr(null);
    try {
      const data = await putLlmProxyBuilds(next);
      setBuilds(data.builds || next);
      if (detailId === bid) setDetailId(null);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setSaving(false);
    }
  };

  const runPreview = async () => {
    if (!draft?.ollama_model?.trim()) {
      setPreviewMsg('Choose an Ollama model first.');
      return;
    }
    setPreviewBusy(true);
    setPreviewMsg(null);
    try {
      const r = await previewLlmProxyBuildModel(String(draft.ollama_model).trim());
      if (r.ok) {
        setPreviewMsg(
          `context_length: ${r.context_length ?? '—'} · thinking: ${r.supports_thinking ? 'yes' : 'no'}`,
        );
      } else setPreviewMsg(r.error || 'Preview failed');
    } catch (e) {
      setPreviewMsg(String(e.message || e));
    } finally {
      setPreviewBusy(false);
    }
  };

  const applySelectedModelDefaults = useCallback(
    async (modelId) => {
      const mid = String(modelId || '').trim();
      if (!mid) return;
      setPreviewBusy(true);
      setPreviewMsg(null);
      try {
        const r = await previewLlmProxyBuildModel(mid);
        const ctxLen = r?.context_length ?? null;
        const thinking = Boolean(r?.supports_thinking);
        setPreviewMsg(`context_length: ${ctxLen ?? '—'} · thinking: ${thinking ? 'yes' : 'no'}`);

        setDraft((prev) => {
          if (!prev || String(prev.ollama_model || '').trim() !== mid) return prev;
          const next = { ...prev };
          const t = proxyDefaults?.temperature;
          const tp = proxyDefaults?.top_p;
          if (String(next.temperature || '').trim() === '' && t != null) next.temperature = String(t);
          if (String(next.top_p || '').trim() === '' && tp != null) next.top_p = String(tp);
          if (String(next.num_ctx || '').trim() === '' && ctxLen != null) next.num_ctx = String(ctxLen);
          if (String(next.backend || '') === 'claw' && String(next.max_agent_steps || '').trim() === '') {
            next.max_agent_steps = String(DEFAULT_CLAW_STEPS);
          }
          return next;
        });
      } catch (e) {
        setPreviewMsg(String(e.message || e));
      } finally {
        setPreviewBusy(false);
      }
    },
    [proxyDefaults],
  );

  if (loading) {
    return (
      <div className="settings-tab settings-tab--fullwidth llm-proxy-tab">
        <p className="settings-intro">Loading builds…</p>
      </div>
    );
  }

  return (
    <div className="settings-tab settings-tab--fullwidth llm-proxy-tab">
      <div className="llm-proxy-header">
        <div className="llm-proxy-header-row">
          <h2>LLM Proxy</h2>
        </div>
        <div className="coreui-pill-tablist" role="tablist" aria-label="LLM Proxy sections">
          {SECTION_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`coreui-pill-tab ${sectionTab === tab.id ? 'coreui-pill-tab-active' : ''}`}
              role="tab"
              aria-selected={sectionTab === tab.id}
              onClick={() => setSectionTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {sectionTab === 'autocomplete' && <LlmProxyAutocompletePanel />}

      {sectionTab === 'builds' && (
        <>
      <p className="settings-intro">
        Each build is a stable <code>model</code> id for <code>POST /v1/chat/completions</code>. The same builds appear
        on <code>GET /v1/models</code> on the main server and on the build proxy port (default 8087).
      </p>
      {(urls.main || urls.build_proxy) && (
        <section className="app-default-card" style={{ marginBottom: 16 }}>
          <div className="dashboard-card-header">
            <h3>OpenAI list endpoints</h3>
          </div>
          <ul className="settings-instructions" style={{ margin: 0 }}>
            {urls.main && (
              <li>
                Main: <code>{urls.main}</code>
              </li>
            )}
            {urls.build_proxy && (
              <li>
                Build proxy: <code>{urls.build_proxy}</code>
              </li>
            )}
          </ul>
        </section>
      )}

      {err && (
        <div className="dashboard-card-error" role="alert" style={{ marginBottom: 12 }}>
          {err}
        </div>
      )}

      <div className="dashboard-card-actions" style={{ marginBottom: 16 }}>
        <button type="button" className="dashboard-primary-btn" onClick={load} disabled={saving}>
          Refresh
        </button>
        <button type="button" className="dashboard-primary-btn" onClick={openNew} disabled={saving || draft}>
          New build
        </button>
      </div>

      <section className="app-default-card">
        <div className="dashboard-card-header">
          <h3>Builds</h3>
        </div>
        {builds.length === 0 && <p className="dashboard-card-muted">No builds yet. Create one to use as API model id.</p>}
        {builds.length > 0 && (
          <div className="dashboard-card-scroll" style={{ maxHeight: 360 }}>
            <table className="llm-proxy-builds-table" style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ textAlign: 'left', borderBottom: '1px solid var(--border, #3334)' }}>
                  <th style={{ padding: '6px 8px' }}>Id</th>
                  <th style={{ padding: '6px 8px' }}>Name</th>
                  <th style={{ padding: '6px 8px' }}>Backend</th>
                  <th style={{ padding: '6px 8px' }} />
                  <th style={{ padding: '6px 8px' }}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {builds.map((b) => (
                  <tr key={b.id} style={{ borderBottom: '1px solid var(--border, #2223)' }}>
                    <td style={{ padding: '6px 8px' }}>
                      <code>{b.id}</code>
                    </td>
                    <td style={{ padding: '6px 8px' }}>{b.display_name || b.id}</td>
                    <td style={{ padding: '6px 8px' }}>{b.backend}</td>
                    <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                      {Array.isArray(b.issues) && b.issues.length > 0 ? (
                        <span
                          className="material-symbols-outlined"
                          style={{ color: 'var(--error, #cf6679)', cursor: 'help' }}
                          title={b.issues.join('\n')}
                          aria-label={`Issues: ${b.issues.join('; ')}`}
                        >
                          error
                        </span>
                      ) : (
                        <span className="dashboard-card-muted">—</span>
                      )}
                    </td>
                    <td style={{ padding: '6px 8px' }}>
                      <button
                        type="button"
                        className="dashboard-primary-btn"
                        style={{ marginRight: 6, fontSize: 12 }}
                        onClick={() => (detailId === b.id ? closeDetails() : openDetails(b.id))}
                      >
                        {detailId === b.id ? 'Hide' : 'Details'}
                      </button>
                      <button
                        type="button"
                        className="dashboard-primary-btn"
                        style={{ marginRight: 6, fontSize: 12 }}
                        onClick={() => openEdit(b)}
                        disabled={!!draft}
                      >
                        Edit
                      </button>
                      <button
                        type="button"
                        className="dashboard-primary-btn"
                        style={{ fontSize: 12 }}
                        onClick={() => deleteBuild(b.id)}
                        disabled={saving}
                      >
                        Delete
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {detailBuild && (
        <CoreUiModal title={`Details: ${detailBuild.id}`} onClose={closeDetails}>
          {detailBuild.issues?.length > 0 && (
            <div className="dashboard-card-error" style={{ marginBottom: 12 }}>
              {detailBuild.issues.map((i) => (
                <div key={i}>{i}</div>
              ))}
            </div>
          )}
          <p className="settings-intro" style={{ marginBottom: 12 }}>
            Use the <code>id</code> field as <code>model</code> in <code>POST /v1/chat/completions</code> (or{' '}
            <code>POST /v1/messages</code>) on the proxy <strong>base URL</strong> — the same host as <code>Main:</code> under
            OpenAI list endpoints above (no separate worker service).
          </p>
          <pre
            style={{
              fontSize: 12,
              overflow: 'auto',
              maxHeight: 520,
              margin: 0,
              padding: 10,
              background: 'var(--md-sys-color-surface-container-highest)',
              color: 'var(--md-sys-color-on-surface)',
              borderRadius: 6,
            }}
          >
            {JSON.stringify(detailBuild, null, 2)}
          </pre>
        </CoreUiModal>
      )}

      {draft && (
        <CoreUiModal title={editingId ? `Edit build: ${editingId}` : 'New build'} onClose={closeForm}>
          <div className="settings-form" style={{ display: 'grid', gap: 12, width: '100%' }}>
            <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              Build id (API model name)
              <input
                className="dashboard-card-field"
                value={draft.id}
                onChange={(e) => setDraft({ ...draft, id: e.target.value })}
                disabled={!!editingId}
                placeholder="e.g. my-dev-build"
              />
            </label>
            <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              Display name
              <input
                className="dashboard-card-field"
                value={draft.display_name}
                onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
              />
            </label>
            <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              Backend
              <select
                className="dashboard-card-field"
                value={draft.backend}
                onChange={(e) => setDraft({ ...draft, backend: e.target.value })}
              >
                <option value="dumb">dumb (RAG + Ollama pipeline)</option>
                <option value="claw">claw (ClawCode agent)</option>
              </select>
            </label>
            {String(draft.backend || '').toLowerCase() === 'claw' && (
              <>
                <label className="dashboard-card-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <input
                    type="checkbox"
                    checked={draft.skills_enabled !== false}
                    onChange={(e) => setDraft({ ...draft, skills_enabled: e.target.checked })}
                  />
                  Enable skill packs (<code>load_skill</code>)
                </label>
                <p className="dashboard-card-muted" style={{ margin: 0 }}>
                  Skill catalog and installs are under <strong>ClawCode Skills</strong> in the Web UI.
                </p>
              </>
            )}
            <p className="dashboard-card-muted" style={{ margin: 0 }}>
              <strong>Ollama model</strong> is required for both backends: dumb uses it for the RAG chat pipeline; claw uses
              the same tag for the ClawCode agent (no separate logical model id).
            </p>
            <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              Ollama model
              <select
                className="dashboard-card-field"
                value={draft.ollama_model}
                onChange={(e) => {
                  const v = e.target.value;
                  setDraft((prev) => ({ ...(prev || {}), ollama_model: v }));
                  void applySelectedModelDefaults(v);
                }}
              >
                <option value="">Select…</option>
                {models.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name || m.id}
                  </option>
                ))}
              </select>
            </label>
            <div className="dashboard-card-actions" style={{ flexWrap: 'wrap' }}>
              <button
                type="button"
                className="dashboard-primary-btn"
                disabled={previewBusy}
                onClick={runPreview}
              >
                Check model (Ollama show)
              </button>
              {previewMsg && <span className="dashboard-card-muted">{previewMsg}</span>}
            </div>
            <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              Prompt template
              <select
                className="dashboard-card-field"
                value={draft.prompt_name}
                onChange={(e) => setDraft({ ...draft, prompt_name: e.target.value })}
              >
                <option value="">Select…</option>
                {prompts.map((p) => (
                  <option key={p.id || p.name} value={p.name || p.id}>
                    {p.name || p.id}
                  </option>
                ))}
              </select>
            </label>
            <label className="dashboard-card-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={!!draft.rag_enabled}
                onChange={(e) => setDraft({ ...draft, rag_enabled: e.target.checked })}
              />
              RAG enabled
            </label>
            <label className="dashboard-card-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={!!draft.web_enabled}
                onChange={(e) => setDraft({ ...draft, web_enabled: e.target.checked })}
              />
              Web supplement enabled
            </label>
            <label className="dashboard-card-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={!!draft.fetch_web_knowledge}
                onChange={(e) => setDraft({ ...draft, fetch_web_knowledge: e.target.checked })}
              />
              Fetch web knowledge
            </label>
            <label className="dashboard-card-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={!!draft.code_only}
                onChange={(e) => setDraft({ ...draft, code_only: e.target.checked })}
              />
              Code only
            </label>
            <label className="dashboard-card-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={!!draft.include_rag_metadata}
                onChange={(e) => setDraft({ ...draft, include_rag_metadata: e.target.checked })}
              />
              Include RAG metadata in response
            </label>
            <label className="dashboard-card-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <input
                type="checkbox"
                checked={!!draft.chat_think}
                onChange={(e) => setDraft({ ...draft, chat_think: e.target.checked })}
              />
              Ollama think (when supported)
            </label>
            <div
              className="dashboard-card-muted"
              style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-start' }}
            >
              <label style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input
                  type="checkbox"
                  checked={!!draft.private}
                  onChange={(e) => setDraft({ ...draft, private: e.target.checked })}
                />
                Private
              </label>
              <p
                style={{
                  margin: 0,
                  fontSize: '0.8125rem',
                  lineHeight: 1.45,
                  opacity: 0.88,
                  maxWidth: '42rem',
                }}
              >
                No proxy rows in the logs database, no Proxy Trace snapshot for this request, and no live or history
                entries in Notifications. Claw builds also skip the in-memory trace buffer and Claw journal rows.
                Does not affect Ollama or OS-level logging.
              </p>
              <p
                style={{
                  margin: '8px 0 0',
                  fontSize: '0.8125rem',
                  lineHeight: 1.45,
                  opacity: 0.88,
                  maxWidth: '42rem',
                }}
              >
                <strong>Cloud models:</strong> if your client or pipeline sends traffic to hosted or third-party model
                APIs, read those providers&apos; privacy policies and terms — they govern how your data is stored and
                processed; Private here only limits traces and logs inside this app.
              </p>
            </div>
            <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              RAG collection override (optional)
              <input
                className="dashboard-card-field"
                value={draft.rag_collection}
                onChange={(e) => setDraft({ ...draft, rag_collection: e.target.value })}
                placeholder="empty = server default"
              />
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
              <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                Context chunk chars
                <input
                  className="dashboard-card-field"
                  inputMode="numeric"
                  value={draft.context_chunk_chars}
                  onChange={(e) => setDraft({ ...draft, context_chunk_chars: e.target.value })}
                  placeholder="YAML / env default"
                />
              </label>
              <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                Context total chars
                <input
                  className="dashboard-card-field"
                  inputMode="numeric"
                  value={draft.context_total_chars}
                  onChange={(e) => setDraft({ ...draft, context_total_chars: e.target.value })}
                  placeholder="YAML / env default"
                />
              </label>
              <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                RAG top_k
                <input
                  className="dashboard-card-field"
                  inputMode="numeric"
                  value={draft.rag_top_k}
                  onChange={(e) => setDraft({ ...draft, rag_top_k: e.target.value })}
                  placeholder="retrieval default"
                />
              </label>
            </div>
            <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              Reasoning level hint (optional)
              <input
                className="dashboard-card-field"
                value={draft.reasoning_level}
                onChange={(e) => setDraft({ ...draft, reasoning_level: e.target.value })}
              />
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                Temperature
                <input
                  className="dashboard-card-field"
                  value={draft.temperature}
                  onChange={(e) => setDraft({ ...draft, temperature: e.target.value })}
                  placeholder="inherit"
                />
              </label>
              <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                Top P
                <input
                  className="dashboard-card-field"
                  value={draft.top_p}
                  onChange={(e) => setDraft({ ...draft, top_p: e.target.value })}
                  placeholder="inherit"
                />
              </label>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                num_ctx
                <input
                  className="dashboard-card-field"
                  value={draft.num_ctx}
                  onChange={(e) => setDraft({ ...draft, num_ctx: e.target.value })}
                  placeholder="Ollama context"
                />
              </label>
              <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                Max agent steps (claw)
                <input
                  className="dashboard-card-field"
                  value={draft.max_agent_steps}
                  onChange={(e) => setDraft({ ...draft, max_agent_steps: e.target.value })}
                  placeholder="1–256"
                />
              </label>
            </div>
            <div className="app-default-card" style={{ marginTop: 4 }}>
              <PipelineCiDiagram
                data={buildModalPipelineData}
                title="LLM proxy pipeline (RAG + supplements)"
                subtitle={
                  String(draft.backend || '').toLowerCase() === 'claw'
                    ? 'Stages reflect this draft on current server settings. Web stages are indicative for claw; edit hybrid/rerank and collection on RAG / Qdrant; skills under ClawCode Skills.'
                    : 'Stages reflect this draft overlaid on current server settings. Edit hybrid/rerank and collection on the RAG / Qdrant tab; Claw skills on ClawCode Skills.'
                }
                compact
              />
            </div>
            <div className="dashboard-card-actions">
              <button type="button" className="dashboard-primary-btn" disabled={saving} onClick={saveForm}>
                Save build
              </button>
              <button type="button" className="dashboard-primary-btn" disabled={saving} onClick={closeForm}>
                Cancel
              </button>
            </div>
          </div>
        </CoreUiModal>
      )}
        </>
      )}
    </div>
  );
}

export default LlmProxyBuildsTab;
