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
} from '../services/api';
import { mergePipelineSnapshot } from '../hooks/useMergedPipelinePreview';
import PipelineCiDiagram from './PipelineCiDiagram';
import PipelineVerticalDiagram from './PipelineVerticalDiagram';
import LlmProxyAutocompletePanel from './LlmProxyAutocompletePanel';
import '../styles/components/DashboardTab.css';
import '../styles/components/SettingsTab.css';
import '../styles/components/LlmProxyTab.css';
import CoreUIPillTabs from './CoreUIPillTabs';

const SECTION_TABS = [
  { id: 'builds', label: 'Builds' },
  { id: 'autocomplete', label: 'Autocomplete' },
];

function mergeBuildDraftIntoPipelinePreview(snapshot, hybridSparse, rerankForRag, draft) {
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
    backend: 'dumb',
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
            <span className="material-symbols-outlined" aria-hidden="true">close</span>
          </button>
        </div>
        <div className="coreui-modal-body">{children}</div>
      </div>
    </div>
  );
}

const WIZARD_STEPS = [
  { id: 'basic', label: 'Basic Info', icon: 'info' },
  { id: 'rag', label: 'RAG', icon: 'search' },
  { id: 'privacy', label: 'Privacy', icon: 'lock' },
  { id: 'parameters', label: 'Parameters', icon: 'tune' },
  { id: 'web', label: 'Web Knowledge', icon: 'language' },
  { id: 'preview', label: 'Pipeline', icon: 'flowchart' },
];

function emptyDraft() {
  return {
    id: '',
    display_name: '',
    backend: 'dumb',
    ollama_model: '',
    prompt_name: '',
    use_prompt_template: true,
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
    sse_streaming: true,
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
  o.use_prompt_template = draft.use_prompt_template !== false;
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
  o.sse_streaming = draft.sse_streaming !== false;
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
  const [openMenuModel, setOpenMenuModel] = useState(null);
  const modelMenuRootRef = useRef(null);
  const [rowBusy, setRowBusy] = useState({});
  const [wizardStep, setWizardStep] = useState(0);
  const [wizardDirection, setWizardDirection] = useState('forward');

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
    if (!openMenuModel) return undefined;
    const onPointerDown = (e) => {
      if (modelMenuRootRef.current?.contains(e.target)) return;
      setOpenMenuModel(null);
    };
    const onKeyDown = (e) => {
      if (e.key === 'Escape') setOpenMenuModel(null);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [openMenuModel]);

  useEffect(() => {
    if (focusSubTab !== 'autocomplete') return;
    setSectionTab('autocomplete');
    if (typeof onFocusSubTabConsumed === 'function') {
      onFocusSubTabConsumed();
    }
  }, [focusSubTab, onFocusSubTabConsumed]);

  const buildModalOpen = Boolean(draft);

  useEffect(() => {
    if (!draft) {
      setBuildModalPipelineSnap(null);
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const [p, r] = await Promise.all([getPipelinePreview(), getRagModelSettings()]);
        if (cancelled) return;
        setBuildModalPipelineSnap(p);
        setBuildModalHybrid(r?.hybrid_sparse_enabled !== false);
        setBuildModalRerank(Boolean(r?.rerank_for_rag));
      } catch {
        if (!cancelled) setBuildModalPipelineSnap(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- draft read from latest render when deps change
  }, [buildModalOpen]);

  const buildModalPipelineData = useMemo(
    () =>
      mergeBuildDraftIntoPipelinePreview(
        buildModalPipelineSnap,
        buildModalHybrid,
        buildModalRerank,
        draft,
      ),
    [buildModalPipelineSnap, buildModalHybrid, buildModalRerank, draft],
  );

  const isFormValid = useMemo(() => {
    if (!draft) return false;
    return Boolean(draft.id?.trim()) && Boolean(draft.ollama_model?.trim());
  }, [draft]);

  const detailBuild = useMemo(
    () => builds.find((x) => x.id === detailId) || null,
    [builds, detailId],
  );

  const openNew = () => {
    setDetailId(null);
    setEditingId(null);
    setDraft(emptyDraft());
    setPreviewMsg(null);
    setWizardStep(0);
    setWizardDirection('forward');
  };

  const openEdit = (b) => {
    setDetailId(null);
    setEditingId(b.id);
    setDraft(buildToDraft(b));
    setPreviewMsg(null);
    setWizardStep(0);
    setWizardDirection('forward');
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
        <CoreUIPillTabs
          tabs={SECTION_TABS}
          value={sectionTab}
          onChange={setSectionTab}
          ariaLabel="LLM Proxy sections"
        />
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
          <div className="llm-proxy-builds-list" role="list" aria-label="LLM Proxy builds">
            {builds.map((b) => {
              const name = b.id || '';
              const busy = rowBusy[name];
              const hasIssues = Array.isArray(b.issues) && b.issues.length > 0;
              const det = detailId === name;
              return (
                <div
                  key={name}
                  className={`llm-proxy-build-row${hasIssues ? ' llm-proxy-build-row--has-issues' : ''}`}
                  role="listitem"
                >
                  <div className="llm-proxy-build-row-header">
                    <div className="llm-proxy-build-main">
                      <div className="llm-proxy-build-title">
                        <span
                          className={`llm-proxy-build-issue-icon material-symbols-outlined${hasIssues ? ' llm-proxy-build-issue-icon--on' : ''}`}
                          aria-hidden="true"
                          title={hasIssues ? b.issues.join('\n') : 'No issues'}
                        >
                          {hasIssues ? 'error' : 'check_circle'}
                        </span>
                        <code title={name}>{name}</code>
                        {b.display_name && b.display_name !== b.id ? (
                          <span className="llm-proxy-build-display-name">{b.display_name}</span>
                        ) : null}
                      </div>
                      <div className="llm-proxy-build-meta">
                        <span className="llm-proxy-build-backend">
                          Backend: <code>{b.backend || 'dumb'}</code>
                        </span>
                        {b.ollama_model ? (
                          <>
                            <span className="llm-proxy-dot" aria-hidden="true">·</span>
                            <span>Ollama: <code>{b.ollama_model}</code></span>
                          </>
                        ) : null}
                        {b.rag_enabled ? (
                          <>
                            <span className="llm-proxy-dot" aria-hidden="true">·</span>
                            <span>RAG enabled</span>
                          </>
                        ) : null}
                      </div>
                    </div>

                    <div
                      className="llm-proxy-build-menu-root"
                      ref={openMenuModel === name ? modelMenuRootRef : null}
                    >
                      <button
                        type="button"
                        className="llm-proxy-build-menu-trigger"
                        aria-haspopup="menu"
                        aria-expanded={openMenuModel === name}
                        aria-label={`Actions for ${name}`}
                        disabled={busy}
                        onClick={() =>
                          setOpenMenuModel((cur) => (cur === name ? null : name))
                        }
                      >
                        <span className="material-symbols-outlined" aria-hidden="true">
                          more_vert
                        </span>
                      </button>
                      {openMenuModel === name ? (
                        <div className="llm-proxy-build-menu" role="menu">
                          <button
                            type="button"
                            className="llm-proxy-build-menu-item"
                            role="menuitem"
                            disabled={busy}
                            onClick={() => {
                              setOpenMenuModel(null);
                              det ? closeDetails() : openDetails(name);
                            }}
                          >
                            <span className="material-symbols-outlined" aria-hidden="true">
                              {det ? 'expand_less' : 'description'}
                            </span>
                            <span>{det ? 'Hide details' : 'Show details'}</span>
                          </button>
                          <button
                            type="button"
                            className="llm-proxy-build-menu-item"
                            role="menuitem"
                            disabled={busy || !!draft}
                            onClick={() => {
                              setOpenMenuModel(null);
                              openEdit(b);
                            }}
                          >
                            <span className="material-symbols-outlined" aria-hidden="true">
                              edit
                            </span>
                            <span>Edit</span>
                          </button>
                          <button
                            type="button"
                            className="llm-proxy-build-menu-item llm-proxy-build-menu-item--danger"
                            role="menuitem"
                            disabled={busy || saving}
                            onClick={() => {
                              setOpenMenuModel(null);
                              deleteBuild(name);
                            }}
                          >
                            <span className="material-symbols-outlined" aria-hidden="true">
                              delete_forever
                            </span>
                            <span>Delete</span>
                          </button>
                        </div>
                      ) : null}
                    </div>
                  </div>

                  {det ? (
                    <div className="llm-proxy-build-details">
                      <div className="llm-proxy-build-details-header">
                        <span className="llm-proxy-build-details-title" id={`llm-proxy-details-title-${name}`}>
                          Details
                        </span>
                        <button
                          type="button"
                          className="llm-proxy-build-details-close"
                          onClick={() => closeDetails()}
                          aria-label="Close details"
                        >
                          <span className="material-symbols-outlined" aria-hidden="true">
                            close
                          </span>
                        </button>
                      </div>
                      <div
                        className="llm-proxy-build-details-body"
                        role="region"
                        aria-labelledby={`llm-proxy-details-title-${name}`}
                      >
                        {hasIssues && (
                          <div className="dashboard-card-error" style={{ marginBottom: 12 }}>
                            {b.issues.map((i) => (
                              <div key={i}>{i}</div>
                            ))}
                          </div>
                        )}
                        <pre>{JSON.stringify(b, null, 2)}</pre>
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}
      </section>

      {draft && (
        <CoreUiModal title={editingId ? `Edit build: ${editingId}` : 'Create new build'} onClose={closeForm}>
          {/* Wizard steps: standard underline tabs (not pill + connector) */}
          <div className="llm-proxy-wizard-steps" role="tablist" aria-label="Build configuration sections">
            {WIZARD_STEPS.map((step, idx) => (
              <button
                key={step.id}
                type="button"
                role="tab"
                aria-selected={idx === wizardStep}
                className={`llm-proxy-wizard-step${
                  idx === wizardStep ? ' llm-proxy-wizard-step-active' : ''
                }${idx < wizardStep ? ' llm-proxy-wizard-step-completed' : ''}`}
                onClick={() => { setWizardStep(idx); setWizardDirection(idx < wizardStep ? 'back' : 'forward'); }}
                data-step={idx + 1}
                aria-label={`Step ${idx + 1}: ${step.label}`}
                aria-current={idx === wizardStep ? 'step' : undefined}
              >
                <span className="llm-proxy-wizard-step-icon material-symbols-outlined" aria-hidden="true">
                  {idx < wizardStep ? 'check' : step.icon}
                </span>
                {step.label}
              </button>
            ))}
          </div>

          {/* Wizard Content - scrollable area */}
          <div className="llm-proxy-wizard-content-wrapper">
            <div className="llm-proxy-wizard-content" key={wizardStep}>
            {/* ── Step 0: Basic Info ── */}
            {wizardStep === 0 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">info</span>
                    Name your build
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    A <strong>build</strong> is a named configuration that API clients reference by the <code>model</code> field.
                    Think of it as a profile — each build wires up a specific Ollama model, RAG settings, and behaviour so
                    you can switch between them instantly without changing client code.
                  </div>
                </div>

                <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  Build id (API model name)
                  <input
                    className="dashboard-card-field"
                    value={draft.id}
                    onChange={(e) => setDraft({ ...draft, id: e.target.value })}
                    disabled={!!editingId}
                    placeholder="e.g. my-dev-build"
                  />
                  <span className="llm-proxy-param-card-hint">This is the <code>model</code> value clients send in API requests. Must be unique. Lowercase, hyphens ok.</span>
                </label>

                <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                  Display name
                  <input
                    className="dashboard-card-field"
                    value={draft.display_name}
                    onChange={(e) => setDraft({ ...draft, display_name: e.target.value })}
                    placeholder="Human-friendly name shown in the UI"
                  />
                  <span className="llm-proxy-param-card-hint">Optional. A readable label for the builds list. Falls back to the build id if empty.</span>
                </label>

                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">smart_toy</span>
                    Choose the Ollama model
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    The Ollama model is the LLM that actually generates responses. The proxy sends it the assembled
                    prompt (system + RAG context + conversation). Pick a model you have pulled locally via <code>ollama pull</code>.
                  </div>
                </div>

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
                  <button type="button" className="dashboard-primary-btn" disabled={previewBusy} onClick={runPreview}>
                    Check model (Ollama show)
                  </button>
                  {previewMsg && <span className="dashboard-card-muted">{previewMsg}</span>}
                </div>

                <div className="llm-proxy-toggle-with-explanation">
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">description</span>
                      Use Prompt Template
                    </span>
                    <input
                      type="checkbox"
                      checked={draft.use_prompt_template !== false}
                      onChange={(e) => setDraft({ ...draft, use_prompt_template: e.target.checked })}
                    />
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    When enabled, the proxy wraps the conversation with a system prompt template (selected below).
                    Templates define the AI's persona, tone, and instructions. Disable only if your client sends its own full system prompt.
                  </p>
                </div>

                {draft.use_prompt_template !== false && (
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
                )}

                <div className="llm-proxy-toggle-with-explanation">
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">psychology</span>
                      Ollama think mode
                    </span>
                    <input
                      type="checkbox"
                      checked={!!draft.chat_think}
                      onChange={(e) => setDraft({ ...draft, chat_think: e.target.checked })}
                    />
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    Enables extended "thinking" output for models that support it (e.g. DeepSeek-R1, QwQ). The model
                    produces a hidden reasoning chain before the final answer, improving quality on complex tasks.
                  </p>
                </div>

                <div className="llm-proxy-toggle-with-explanation">
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">stream</span>
                      Token-by-token SSE streaming
                    </span>
                    <input
                      type="checkbox"
                      checked={draft.sse_streaming !== false}
                      onChange={(e) => setDraft({ ...draft, sse_streaming: e.target.checked })}
                    />
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    When on, tokens stream from Ollama to the client one-by-one in real time. When off, the proxy
                    collects the full response first, then sends it as a single SSE burst — useful if streaming causes
                    incomplete tool calls or flaky clients.
                  </p>
                </div>
              </div>
            )}

            {/* ── Step 1: RAG ── */}
            {wizardStep === 1 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">search</span>
                    What is RAG and why does it matter?
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    <strong>RAG (Retrieval-Augmented Generation)</strong> supercharges the AI with your own documents.
                    Instead of relying solely on the model's training data, RAG searches a vector database (Qdrant)
                    for relevant passages <em>before</em> generating a response, then injects them into the prompt.
                    <ul>
                      <li><strong>Accurate answers</strong> — the model cites your docs, not just its memory</li>
                      <li><strong>Up-to-date</strong> — works with docs added or changed today, not last year's training cut-off</li>
                      <li><strong>Domain-specific</strong> — private codebases, internal wikis, API docs — anything you index</li>
                      <li><strong>Reduced hallucinations</strong> — grounded context keeps the model honest</li>
                    </ul>
                    Without RAG, the model answers from general knowledge only. With RAG, it answers from <em>your</em> knowledge base.
                  </div>
                </div>

                <div className="llm-proxy-toggle-with-explanation" style={{ borderLeft: '3px solid var(--md-sys-color-primary)' }}>
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">search</span>
                      Enable RAG for this build
                    </span>
                    <input
                      type="checkbox"
                      checked={!!draft.rag_enabled}
                      onChange={(e) => setDraft({ ...draft, rag_enabled: e.target.checked })}
                    />
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    When enabled, every chat request will search your Qdrant collections for relevant context before
                    calling the LLM. Disable if you want a pure passthrough to the Ollama model with no document retrieval.
                  </p>
                </div>

                {draft.rag_enabled && (
                  <>
                    <div className="llm-proxy-rag-features">
                      <div className="llm-proxy-rag-feature">
                        <span className="llm-proxy-rag-feature-icon material-symbols-outlined" aria-hidden="true">database</span>
                        <span className="llm-proxy-rag-feature-text"><strong>Vector search</strong> — embeds the query and finds the closest document chunks by semantic similarity</span>
                      </div>
                      <div className="llm-proxy-rag-feature">
                        <span className="llm-proxy-rag-feature-icon material-symbols-outlined" aria-hidden="true">merge_type</span>
                        <span className="llm-proxy-rag-feature-text"><strong>Hybrid fusion</strong> — combines dense + sparse vectors with RRF for better recall (config in RAG / Qdrant)</span>
                      </div>
                      <div className="llm-proxy-rag-feature">
                        <span className="llm-proxy-rag-feature-icon material-symbols-outlined" aria-hidden="true">filter_alt</span>
                        <span className="llm-proxy-rag-feature-text"><strong>Smart filtering</strong> — auto-skips RAG for greetings and small talk; uses keyword triggers for technical questions</span>
                      </div>
                      <div className="llm-proxy-rag-feature">
                        <span className="llm-proxy-rag-feature-icon material-symbols-outlined" aria-hidden="true">rank</span>
                        <span className="llm-proxy-rag-feature-text"><strong>Reranking</strong> — optional LLM-based rerank of top candidates for precision (config in RAG / Qdrant)</span>
                      </div>
                    </div>

                    <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }}>
                      RAG collection override
                      <input
                        className="dashboard-card-field"
                        value={draft.rag_collection}
                        onChange={(e) => setDraft({ ...draft, rag_collection: e.target.value })}
                        placeholder="empty = server default"
                      />
                      <span className="llm-proxy-param-card-hint">Leave empty to use the server's default collection. Set a name to search a specific Qdrant collection for this build.</span>
                    </label>

                    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
                      <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        Context chunk chars
                        <input
                          className="dashboard-card-field"
                          inputMode="numeric"
                          value={draft.context_chunk_chars}
                          onChange={(e) => setDraft({ ...draft, context_chunk_chars: e.target.value })}
                          placeholder="YAML default"
                        />
                        <span className="llm-proxy-param-card-hint">Max characters per retrieved chunk sent to the model.</span>
                      </label>
                      <label className="dashboard-card-muted" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
                        Context total chars
                        <input
                          className="dashboard-card-field"
                          inputMode="numeric"
                          value={draft.context_total_chars}
                          onChange={(e) => setDraft({ ...draft, context_total_chars: e.target.value })}
                          placeholder="YAML default"
                        />
                        <span className="llm-proxy-param-card-hint">Total RAG context budget across all chunks.</span>
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
                        <span className="llm-proxy-param-card-hint">Number of document chunks to retrieve from Qdrant.</span>
                      </label>
                    </div>

                    <div className="llm-proxy-toggle-with-explanation">
                      <div className="llm-proxy-toggle-row">
                        <span className="llm-proxy-toggle-label">
                          <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">code</span>
                          Code only mode
                        </span>
                        <input
                          type="checkbox"
                          checked={!!draft.code_only}
                          onChange={(e) => setDraft({ ...draft, code_only: e.target.checked })}
                        />
                      </div>
                      <p className="llm-proxy-toggle-explanation">
                        Restricts RAG retrieval to code documents only (snippets, source files). Useful for coding assistants that shouldn't pull prose docs.
                      </p>
                    </div>

                    <div className="llm-proxy-toggle-with-explanation">
                      <div className="llm-proxy-toggle-row">
                        <span className="llm-proxy-toggle-label">
                          <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">metadata</span>
                          Include RAG metadata in response
                        </span>
                        <input
                          type="checkbox"
                          checked={!!draft.include_rag_metadata}
                          onChange={(e) => setDraft({ ...draft, include_rag_metadata: e.target.checked })}
                        />
                      </div>
                      <p className="llm-proxy-toggle-explanation">
                        Appends citation metadata (source file, chunk id, score) to the API response so clients can show where the answer came from.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* ── Step 2: Privacy ── */}
            {wizardStep === 2 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">lock</span>
                    Privacy &amp; logging
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    By default, the proxy logs every request: it stores a row in the journal database, creates a live
                    trace snapshot, and may show notifications. <strong>Private mode</strong> turns all of that off for
                    this build — no database rows, no traces, no notifications.
                    <ul>
                      <li><strong>When to enable Private:</strong> sensitive prompts, personal data, confidential code reviews, or any workflow where you don't want a record</li>
                      <li><strong>When to keep it off:</strong> normal development, debugging, or when you want the Traces and Journal tabs to show request history</li>
                    </ul>
                  </div>
                </div>

                <div className="llm-proxy-toggle-with-explanation" style={{ borderLeft: '3px solid var(--md-sys-color-tertiary)' }}>
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">visibility_off</span>
                      Private mode
                    </span>
                    <input
                      type="checkbox"
                      checked={!!draft.private}
                      onChange={(e) => setDraft({ ...draft, private: e.target.checked })}
                    />
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    No proxy rows in the logs database, no live trace snapshot for this request, and no live or history
                    entries in Notifications. Does not affect Ollama or OS-level logging.
                  </p>
                  {draft.private && (
                    <p className="llm-proxy-toggle-explanation" style={{ marginTop: 8, color: 'var(--md-sys-color-on-tertiary-container)' }}>
                      <strong>⚠ Cloud models:</strong> if your client or pipeline sends traffic to hosted or third-party model
                      APIs, read those providers' privacy policies and terms — they govern how your data is stored and
                      processed; Private here only limits traces and logs inside this app.
                    </p>
                  )}
                </div>

                <div className="llm-proxy-info-card" style={{ opacity: draft.private ? 0.6 : 1 }}>
                  <h3 className="llm-proxy-info-card-title" style={{ fontSize: '1rem' }}>
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">visibility</span>
                    What gets logged when Private is off
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    <ul>
                      <li><strong>Journal</strong> — full request/response stored in SQLite for the Journal tab</li>
                      <li><strong>Traces</strong> — live in-memory snapshot of the pipeline stages (RAG hits, timing, etc.)</li>
                      <li><strong>Notifications</strong> — completion alerts in the notification center</li>
                    </ul>
                    All of the above are disabled when Private is on.
                  </div>
                </div>
              </div>
            )}

            {/* ── Step 3: Parameters ── */}
            {wizardStep === 3 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">tune</span>
                    Fine-tune the model
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    These parameters control how the LLM generates text. Leave a field empty to inherit the server's
                    default value. Each one is explained below — no PhD required.
                  </div>
                </div>

                <div className="llm-proxy-param-card">
                  <div className="llm-proxy-param-card-header">
                    <span className="llm-proxy-param-card-icon material-symbols-outlined" aria-hidden="true">thermostat</span>
                    <h4 className="llm-proxy-param-card-title">Temperature</h4>
                  </div>
                  <p className="llm-proxy-param-card-description">
                    Controls <strong>creativity vs. consistency</strong>. Low values (0.0–0.3) make the model focused and
                    deterministic — great for code, facts, and precise answers. High values (0.7–1.5) make it more
                    creative and varied — better for brainstorming and storytelling. Think of it as a dial between
                    "robot" and "poet".
                  </p>
                  <input
                    className="dashboard-card-field llm-proxy-param-card-field"
                    value={draft.temperature}
                    onChange={(e) => setDraft({ ...draft, temperature: e.target.value })}
                    placeholder="inherit (server default)"
                    inputMode="decimal"
                  />
                  <p className="llm-proxy-param-card-hint">Range: 0.0 – 2.0. Typical: 0.1 for code, 0.7 for chat, 1.0+ for creative writing.</p>
                </div>

                <div className="llm-proxy-param-card">
                  <div className="llm-proxy-param-card-header">
                    <span className="llm-proxy-param-card-icon material-symbols-outlined" aria-hidden="true">filter_list</span>
                    <h4 className="llm-proxy-param-card-title">Top P (nucleus sampling)</h4>
                  </div>
                  <p className="llm-proxy-param-card-description">
                    Another way to control randomness. Instead of cutting off low-probability tokens entirely (like
                    Temperature), <strong>Top P</strong> keeps the smallest set of tokens whose cumulative probability
                    exceeds P. Low P (0.1) = only the most likely tokens. High P (0.9+) = almost all tokens are
                    considered. In practice, you usually adjust <em>either</em> Temperature <em>or</em> Top P, not both.
                  </p>
                  <input
                    className="dashboard-card-field llm-proxy-param-card-field"
                    value={draft.top_p}
                    onChange={(e) => setDraft({ ...draft, top_p: e.target.value })}
                    placeholder="inherit (server default)"
                    inputMode="decimal"
                  />
                  <p className="llm-proxy-param-card-hint">Range: 0.0 – 1.0. Typical: 0.9 for general use, 0.1 for strict/focused output.</p>
                </div>

                <div className="llm-proxy-param-card">
                  <div className="llm-proxy-param-card-header">
                    <span className="llm-proxy-param-card-icon material-symbols-outlined" aria-hidden="true">context_memory</span>
                    <h4 className="llm-proxy-param-card-title">num_ctx (context window)</h4>
                  </div>
                  <p className="llm-proxy-param-card-description">
                    The <strong>total number of tokens</strong> the model can "see" at once — including the system prompt,
                    RAG context, conversation history, and the new question. A larger window means more context but
                    uses more memory and is slower. The model's maximum is set by Ollama (shown when you click
                    "Check model"). Setting this lower than the max saves resources for short conversations.
                  </p>
                  <input
                    className="dashboard-card-field llm-proxy-param-card-field"
                    value={draft.num_ctx}
                    onChange={(e) => setDraft({ ...draft, num_ctx: e.target.value })}
                    placeholder="inherit (model default)"
                    inputMode="numeric"
                  />
                  <p className="llm-proxy-param-card-hint">Example: 8192 for small models, 32768+ for large context models. Auto-filled when you select an Ollama model above.</p>
                </div>

                <div className="llm-proxy-param-card">
                  <div className="llm-proxy-param-card-header">
                    <span className="llm-proxy-param-card-icon material-symbols-outlined" aria-hidden="true">route</span>
                    <h4 className="llm-proxy-param-card-title">Max agent steps</h4>
                  </div>
                  <p className="llm-proxy-param-card-description">
                    When the model uses <strong>tool calls</strong> (function calling), each round of "think → call tool →
                    read result → think again" is one agent step. This limit prevents infinite loops. A step count of 1
                    means no tool use at all (single-shot). Higher values allow multi-step reasoning chains.
                  </p>
                  <input
                    className="dashboard-card-field llm-proxy-param-card-field"
                    value={draft.max_agent_steps}
                    onChange={(e) => setDraft({ ...draft, max_agent_steps: e.target.value })}
                    placeholder="inherit (1–256)"
                    inputMode="numeric"
                  />
                  <p className="llm-proxy-param-card-hint">Range: 1–256. Typical: 1 for simple chat, 5–10 for tool-using agents, 50+ for complex agentic workflows.</p>
                </div>


              </div>
            )}

            {/* ── Step 4: Web Knowledge ── */}
            {wizardStep === 4 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">language</span>
                    Web Knowledge — fresh info beyond your docs
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    Your RAG database contains <em>your</em> indexed documents, but what about the latest library release,
                    a new API, or a recent changelog? <strong>Web Knowledge</strong> supplements RAG with live internet
                    data — search results, web pages, and GitHub-sourced documentation — so the model can answer
                    questions about things that happened <em>after</em> your last index run.
                  </div>
                </div>

                <div className="llm-proxy-toggle-with-explanation" style={{ borderLeft: '3px solid var(--md-sys-color-tertiary)' }}>
                  <div className="llm-proxy-toggle-row">
                    <span className="llm-proxy-toggle-label">
                      <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">public</span>
                      Web supplement enabled
                    </span>
                    <input
                      type="checkbox"
                      checked={!!draft.web_enabled}
                      onChange={(e) => setDraft({ ...draft, web_enabled: e.target.checked })}
                    />
                  </div>
                  <p className="llm-proxy-toggle-explanation">
                    Master switch for all web-based features below. When off, no web data is fetched for this build —
                    only your local RAG collection is used.
                  </p>
                </div>

                {draft.web_enabled && (
                  <>
                    <div className="llm-proxy-web-features">
                      <div className="llm-proxy-web-feature-item">
                        <span className="llm-proxy-web-feature-title">
                          <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: 18, color: 'var(--md-sys-color-tertiary)' }}>travel_explore</span>
                          DuckDuckGo search snippets
                        </span>
                        <p className="llm-proxy-web-feature-desc">
                          Fetches short text snippets from DuckDuckGo search results. Free, no API key needed.
                          Great for quick facts, version numbers, and recent announcements.
                        </p>
                        <div className="llm-proxy-toggle-row" style={{ marginTop: 4 }}>
                          <span className="llm-proxy-toggle-label" style={{ fontSize: '0.8125rem' }}>Enable DDG news</span>
                          <input
                            type="checkbox"
                            checked={!!draft.web_interaction_ddg_news}
                            onChange={(e) => setDraft({ ...draft, web_interaction_ddg_news: e.target.checked })}
                          />
                        </div>
                      </div>

                      <div className="llm-proxy-web-feature-item">
                        <span className="llm-proxy-web-feature-title">
                          <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: 18, color: 'var(--md-sys-color-tertiary)' }}>web</span>
                          Fetch web pages
                        </span>
                        <p className="llm-proxy-web-feature-desc">
                          When a search result looks promising, the proxy can fetch and extract the full page content
                          for deeper context. Uses more tokens but provides much richer information.
                        </p>
                        <div className="llm-proxy-toggle-row" style={{ marginTop: 4 }}>
                          <span className="llm-proxy-toggle-label" style={{ fontSize: '0.8125rem' }}>Enable page fetching</span>
                          <input
                            type="checkbox"
                            checked={!!draft.web_interaction_fetch_page}
                            onChange={(e) => setDraft({ ...draft, web_interaction_fetch_page: e.target.checked })}
                          />
                        </div>
                      </div>

                      <div className="llm-proxy-web-feature-item">
                        <span className="llm-proxy-web-feature-title">
                          <span className="material-symbols-outlined" aria-hidden="true" style={{ fontSize: 18, color: 'var(--md-sys-color-tertiary)' }}>menu_book</span>
                          Wikipedia lookup
                        </span>
                        <p className="llm-proxy-web-feature-desc">
                          Searches Wikipedia for encyclopedic background on topics. Useful for general knowledge,
                          definitions, and historical context.
                        </p>
                        <div className="llm-proxy-toggle-row" style={{ marginTop: 4 }}>
                          <span className="llm-proxy-toggle-label" style={{ fontSize: '0.8125rem' }}>Enable Wikipedia</span>
                          <input
                            type="checkbox"
                            checked={!!draft.web_interaction_wikipedia}
                            onChange={(e) => setDraft({ ...draft, web_interaction_wikipedia: e.target.checked })}
                          />
                        </div>
                      </div>
                    </div>

                    <div className="llm-proxy-toggle-with-explanation" style={{ marginTop: 8 }}>
                      <div className="llm-proxy-toggle-row">
                        <span className="llm-proxy-toggle-label">
                          <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">cloud_download</span>
                          Fetch web knowledge (GitHub docs)
                        </span>
                        <input
                          type="checkbox"
                          checked={!!draft.fetch_web_knowledge}
                          onChange={(e) => setDraft({ ...draft, fetch_web_knowledge: e.target.checked })}
                        />
                      </div>
                      <p className="llm-proxy-toggle-explanation">
                        Enables merged multi-collection retrieval and background GitHub markdown refresh via
                        <code>external_docs_rag</code>. Pulls documentation from public GitHub repos (rate-limited via
                        the public API) and indexes them into a separate Qdrant collection. Ideal for framework docs,
                        SDK references, and open-source project wikis.
                      </p>
                    </div>

                    <div className="llm-proxy-toggle-with-explanation">
                      <div className="llm-proxy-toggle-row">
                        <span className="llm-proxy-toggle-label">
                          <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">toggle_on</span>
                          Web on keyword triggers
                        </span>
                        <input
                          type="checkbox"
                          checked={draft.web_interaction_on_keywords !== false}
                          onChange={(e) => setDraft({ ...draft, web_interaction_on_keywords: e.target.checked })}
                        />
                      </div>
                      <p className="llm-proxy-toggle-explanation">
                        Automatically triggers web search when the query contains keywords that suggest the user needs
                        fresh information (e.g. "latest", "new", "release", "changelog").
                      </p>
                    </div>

                    <div className="llm-proxy-toggle-with-explanation">
                      <div className="llm-proxy-toggle-row">
                        <span className="llm-proxy-toggle-label">
                          <span className="llm-proxy-toggle-icon material-symbols-outlined" aria-hidden="true">help</span>
                          Web on low-confidence framework questions
                        </span>
                        <input
                          type="checkbox"
                          checked={draft.web_interaction_on_low_confidence_framework !== false}
                          onChange={(e) => setDraft({ ...draft, web_interaction_on_low_confidence_framework: e.target.checked })}
                        />
                      </div>
                      <p className="llm-proxy-toggle-explanation">
                        When RAG returns low-confidence results for framework-related questions, automatically supplements
                        with web search to fill the gap.
                      </p>
                    </div>
                  </>
                )}
              </div>
            )}

            {/* ── Step 5: Pipeline Preview ── */}
            {wizardStep === 5 && (
              <div className="llm-proxy-wizard-step-panel">
                <div className="llm-proxy-info-card">
                  <h3 className="llm-proxy-info-card-title">
                    <span className="llm-proxy-info-card-title-icon material-symbols-outlined" aria-hidden="true">flowchart</span>
                    Pipeline preview
                  </h3>
                  <div className="llm-proxy-info-card-body">
                    This diagram shows the full request pipeline for your build — from the incoming API request through
                    RAG retrieval, web supplements, and the final LLM call. It reflects your current settings overlaid
                    on the server defaults.
                  </div>
                </div>

                <PipelineVerticalDiagram data={buildModalPipelineData} />

                <div className="llm-proxy-build-summary">
                  <h3 className="llm-proxy-build-summary-title">
                    <span className="material-symbols-outlined" aria-hidden="true">summarize</span>
                    Build summary
                  </h3>
                  <div className="llm-proxy-build-summary-grid">
                    <div className="llm-proxy-build-summary-row">
                      <span className="llm-proxy-build-summary-key">Build id</span>
                      <code className="llm-proxy-build-summary-val">{draft.id || '—'}</code>
                    </div>
                    <div className="llm-proxy-build-summary-row">
                      <span className="llm-proxy-build-summary-key">Display name</span>
                      <span className="llm-proxy-build-summary-val">{draft.display_name || '—'}</span>
                    </div>
                    <div className="llm-proxy-build-summary-row">
                      <span className="llm-proxy-build-summary-key">Ollama model</span>
                      <code className="llm-proxy-build-summary-val">{draft.ollama_model || '—'}</code>
                    </div>
                    <div className="llm-proxy-build-summary-row">
                      <span className="llm-proxy-build-summary-key">RAG</span>
                      <span className={`llm-proxy-build-summary-val${draft.rag_enabled ? ' llm-proxy-build-summary-val--on' : ' llm-proxy-build-summary-val--off'}`}>
                        {draft.rag_enabled ? 'Enabled' : 'Disabled'}{draft.rag_enabled && draft.rag_collection ? ` · ${draft.rag_collection}` : ''}
                      </span>
                    </div>
                    <div className="llm-proxy-build-summary-row">
                      <span className="llm-proxy-build-summary-key">Private</span>
                      <span className={`llm-proxy-build-summary-val${draft.private ? ' llm-proxy-build-summary-val--on' : ' llm-proxy-build-summary-val--off'}`}>
                        {draft.private ? 'On' : 'Off'}
                      </span>
                    </div>
                    <div className="llm-proxy-build-summary-row">
                      <span className="llm-proxy-build-summary-key">Web</span>
                      <span className={`llm-proxy-build-summary-val${draft.web_enabled ? ' llm-proxy-build-summary-val--on' : ' llm-proxy-build-summary-val--off'}`}>
                        {draft.web_enabled ? 'Enabled' : 'Disabled'}
                      </span>
                    </div>
                    <div className="llm-proxy-build-summary-row">
                      <span className="llm-proxy-build-summary-key">Temperature</span>
                      <span className="llm-proxy-build-summary-val">{draft.temperature || 'Inherit'}</span>
                    </div>
                    <div className="llm-proxy-build-summary-row">
                      <span className="llm-proxy-build-summary-key">Top P</span>
                      <span className="llm-proxy-build-summary-val">{draft.top_p || 'Inherit'}</span>
                    </div>
                    <div className="llm-proxy-build-summary-row">
                      <span className="llm-proxy-build-summary-key">num_ctx</span>
                      <span className="llm-proxy-build-summary-val">{draft.num_ctx || 'Inherit'}</span>
                    </div>
                    <div className="llm-proxy-build-summary-row">
                      <span className="llm-proxy-build-summary-key">Max agent steps</span>
                      <span className="llm-proxy-build-summary-val">{draft.max_agent_steps || 'Inherit'}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
          </div>

          {/* Wizard Navigation - sticky footer */}
            <div className="llm-proxy-wizard-nav">
              <div className="llm-proxy-wizard-nav-left">
                {wizardStep > 0 && (
                  <button
                    type="button"
                    className="dashboard-primary-btn"
                    onClick={() => { setWizardStep(wizardStep - 1); setWizardDirection('back'); }}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 18, marginRight: 4 }} aria-hidden="true">arrow_back</span>
                    Back
                  </button>
                )}
              </div>
              <div className="llm-proxy-wizard-nav-center">
                {wizardStep < WIZARD_STEPS.length - 1 && (
                  <button
                    type="button"
                    className="dashboard-primary-btn"
                    disabled={saving}
                    onClick={saveForm}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 18, marginRight: 4 }} aria-hidden="true">save</span>
                    {saving ? 'Saving...' : 'Save build'}
                  </button>
                )}
              </div>
              <div className="llm-proxy-wizard-nav-right">
                {wizardStep < WIZARD_STEPS.length - 1 ? (
                  <button
                    type="button"
                    className="dashboard-primary-btn"
                    onClick={() => { setWizardStep(wizardStep + 1); setWizardDirection('forward'); }}
                  >
                    Next
                    <span className="material-symbols-outlined" style={{ fontSize: 18, marginLeft: 4 }} aria-hidden="true">arrow_forward</span>
                  </button>
                ) : (
                  <button
                    type="button"
                    className="dashboard-primary-btn"
                    disabled={saving}
                    onClick={saveForm}
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 18, marginRight: 4 }} aria-hidden="true">save</span>
                    {saving ? 'Saving...' : 'Save build'}
                  </button>
                )}
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
