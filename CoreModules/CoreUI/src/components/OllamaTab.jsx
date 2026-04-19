import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  getOllamaStatus,
  getOllamaLibrary,
  patchOllamaHidden,
  showOllamaModel,
  deleteOllamaModel,
  pullOllamaModel,
  startOllama,
  stopOllama,
} from '../services/api';
import '../styles/components/DashboardTab.css';
import '../styles/components/OllamaTab.css';
import {
  extractFamilyFromShowPayload,
  getOllamaModelBrandKey,
  getOllamaModelBrandKeyFromFamily,
  OLLAMA_BRAND_ICON_URL,
} from '../utils/ollamaModelBrandIcons';

function formatBytes(n) {
  if (n == null || Number.isNaN(Number(n))) return '—';
  const v = Number(n);
  if (v === 0) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  let i = 0;
  let x = v;
  while (x >= 1024 && i < units.length - 1) {
    x /= 1024;
    i += 1;
  }
  return `${x < 10 && i > 0 ? x.toFixed(1) : Math.round(x)} ${units[i]}`;
}

function stripGgufSuffix(title) {
  const s = (title || '').trim();
  if (!s || !/-gguf$/i.test(s)) return s;
  const cut = s.slice(0, -5).replace(/-+$/u, '').trim();
  return cut || s;
}

function parseOllamaModelDisplayParts(fullId) {
  const raw = (fullId || '').trim();
  if (!raw) return { title: '', quant: null, full: raw };
  const c = raw.lastIndexOf(':');
  let basePath = raw;
  let quant = null;
  if (c > 0 && c < raw.length - 1) {
    basePath = raw.slice(0, c);
    const q = raw.slice(c + 1).trim();
    quant = q || null;
  }
  const slash = basePath.lastIndexOf('/');
  let title = (slash >= 0 ? basePath.slice(slash + 1) : basePath).trim() || raw;
  title = stripGgufSuffix(title);
  return { title, quant, full: raw };
}

function isCloudModelName(raw) {
  const name = (raw || '').trim();
  if (!name) return false;
  const i = name.lastIndexOf(':');
  const tag = i >= 0 ? name.slice(i + 1) : name;
  return tag.toLowerCase().endsWith('cloud');
}

function sortModelsForDisplay(list) {
  if (!Array.isArray(list)) return [];
  return [...list].sort((a, b) => {
    const an = (a?.name || '').trim();
    const bn = (b?.name || '').trim();
    const ac = isCloudModelName(an);
    const bc = isCloudModelName(bn);
    if (ac !== bc) return ac ? -1 : 1;
    return an.localeCompare(bn, undefined, { sensitivity: 'base', numeric: true });
  });
}

function formatModifiedAt(raw) {
  if (raw == null || raw === '') return '—';
  const s = String(raw).trim();
  if (!s) return '—';
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return s;
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(d);
}

function OllamaTab({ onErrorStateChange }) {
  const [status, setStatus] = useState(null);
  const [library, setLibrary] = useState(null);
  const [libraryLoading, setLibraryLoading] = useState(true);
  const [libraryMsg, setLibraryMsg] = useState(null);
  const [statusBusy, setStatusBusy] = useState(false);
  const [expanded, setExpanded] = useState({});
  const [detailsLoading, setDetailsLoading] = useState({});
  const [pullName, setPullName] = useState('');
  const [pulling, setPulling] = useState(false);
  const [pullStatus, setPullStatus] = useState('');
  const [pullPct, setPullPct] = useState(null);
  const [pullErr, setPullErr] = useState(null);
  const [rowBusy, setRowBusy] = useState({});
  const pullAbortRef = useRef(null);
  const pullHadErrorRef = useRef(false);
  const [openMenuModel, setOpenMenuModel] = useState(null);
  const modelMenuRootRef = useRef(null);
  /** Persist Ollama `family` from show() so the brand icon stays after details are collapsed. */
  const [familyHintByName, setFamilyHintByName] = useState({});
  /** Invalidate in-flight show() when the details panel is closed so a late response cannot reopen it. */
  const detailsRequestGenRef = useRef({});

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

  const refreshStatus = useCallback(async () => {
    try {
      const s = await getOllamaStatus();
      setStatus(s);
    } catch (e) {
      setStatus({ running: false, error: e?.message || String(e) });
    }
  }, []);

  const refreshLibrary = useCallback(async () => {
    setLibraryLoading(true);
    setLibraryMsg(null);
    try {
      const data = await getOllamaLibrary();
      setLibrary(data);
      if (!data.ok && data.error) {
        setLibraryMsg(data.error);
      }
    } catch (e) {
      setLibrary(null);
      setLibraryMsg(e?.message || String(e));
    } finally {
      setLibraryLoading(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
    refreshLibrary();
  }, [refreshStatus, refreshLibrary]);

  const tabError =
    Boolean(libraryMsg && (!library || !library?.ok)) || Boolean(pullErr);
  useEffect(() => {
    onErrorStateChange?.(tabError);
  }, [tabError, onErrorStateChange]);

  const handleStartStop = async () => {
    setStatusBusy(true);
    try {
      if (status?.running) {
        await stopOllama();
      } else {
        await startOllama();
      }
      await refreshStatus();
    } catch (e) {
      setLibraryMsg(e?.message || String(e));
    } finally {
      setStatusBusy(false);
    }
  };

  const toggleHidden = async (name, currentlyHidden) => {
    setRowBusy((b) => ({ ...b, [name]: true }));
    try {
      if (currentlyHidden) {
        await patchOllamaHidden({ remove: [name], add: [] });
      } else {
        await patchOllamaHidden({ add: [name], remove: [] });
      }
      await refreshLibrary();
    } catch (e) {
      setLibraryMsg(e?.message || String(e));
    } finally {
      setRowBusy((b) => ({ ...b, [name]: false }));
    }
  };

  const bumpDetailsRequestGen = (name) => {
    const next = (detailsRequestGenRef.current[name] || 0) + 1;
    detailsRequestGenRef.current[name] = next;
    return next;
  };

  const closeDetails = (name) => {
    bumpDetailsRequestGen(name);
    setExpanded((x) => ({ ...x, [name]: null }));
    setDetailsLoading((d) => ({ ...d, [name]: false }));
  };

  const toggleDetails = async (name) => {
    const open = expanded[name];
    if (open) {
      closeDetails(name);
      return;
    }
    const gen = bumpDetailsRequestGen(name);
    setDetailsLoading((d) => ({ ...d, [name]: true }));
    try {
      const res = await showOllamaModel(name);
      if (detailsRequestGenRef.current[name] !== gen) return;
      if (res.ok && res.details) {
        const fam = extractFamilyFromShowPayload(res.details);
        if (fam) {
          setFamilyHintByName((m) => ({ ...m, [name]: fam }));
        }
        setExpanded((x) => ({ ...x, [name]: res.details }));
      } else {
        setExpanded((x) => ({ ...x, [name]: { error: res.error || 'Unknown error' } }));
      }
    } catch (e) {
      if (detailsRequestGenRef.current[name] !== gen) return;
      setExpanded((x) => ({ ...x, [name]: { error: e?.message || String(e) } }));
    } finally {
      if (detailsRequestGenRef.current[name] === gen) {
        setDetailsLoading((d) => ({ ...d, [name]: false }));
      }
    }
  };

  const handleDelete = async (name) => {
    if (!window.confirm(`Delete model "${name}" from Ollama? This cannot be undone.`)) {
      return;
    }
    setRowBusy((b) => ({ ...b, [name]: true }));
    try {
      await deleteOllamaModel(name);
      bumpDetailsRequestGen(name);
      setExpanded((x) => {
        const n = { ...x };
        delete n[name];
        return n;
      });
      setFamilyHintByName((m) => {
        if (!(name in m)) return m;
        const next = { ...m };
        delete next[name];
        return next;
      });
      await refreshLibrary();
    } catch (e) {
      setLibraryMsg(e?.message || String(e));
    } finally {
      setRowBusy((b) => ({ ...b, [name]: false }));
    }
  };

  const cancelPull = () => {
    pullAbortRef.current?.abort();
    pullAbortRef.current = null;
  };

  const handlePull = async () => {
    const model = pullName.trim();
    if (!model) {
      setPullErr('Enter a model name to pull.');
      return;
    }
    cancelPull();
    const ac = new AbortController();
    pullAbortRef.current = ac;
    pullHadErrorRef.current = false;
    setPulling(true);
    setPullErr(null);
    setPullStatus('Starting…');
    setPullPct(null);
    try {
      await pullOllamaModel({
        model,
        onLine: (obj) => {
          if (obj && typeof obj.error === 'string') {
            pullHadErrorRef.current = true;
            setPullErr(obj.error);
            setPullStatus('');
            return;
          }
          const st = obj?.status != null ? String(obj.status) : '';
          if (st) setPullStatus(st);
          const c = obj?.completed;
          const t = obj?.total;
          if (typeof c === 'number' && typeof t === 'number' && t > 0) {
            setPullPct(Math.min(100, Math.round((100 * c) / t)));
          }
        },
        signal: ac.signal,
      });
      if (!pullHadErrorRef.current && !ac.signal.aborted) {
        setPullStatus((s) => s || 'Done');
      }
      await refreshLibrary();
    } catch (e) {
      if (e?.name === 'AbortError') {
        setPullStatus('Cancelled');
      } else {
        setPullErr(e?.message || String(e));
      }
    } finally {
      setPulling(false);
      pullAbortRef.current = null;
    }
  };

  const models = library?.models || [];
  const sortedModels = useMemo(() => sortModelsForDisplay(models), [library]);
  const running = Boolean(status?.running);
  const url = status?.url || library?.url || null;
  const statusError = status?.error ? String(status.error) : null;

  return (
    <div className="dashboard-tab ollama-tab">
      <div className="tab-page-header">
        <h2>Ollama</h2>
      </div>

      <section className="app-default-card" aria-labelledby="ollama-status-heading">
        <div className="dashboard-card-header">
          <h2 id="ollama-status-heading">Service</h2>
          <div className="dashboard-card-actions">
            <button
              type="button"
              className="dashboard-secondary-btn"
              onClick={() => {
                refreshStatus();
                refreshLibrary();
              }}
              disabled={libraryLoading}
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

        <div className="ollama-tab__status-grid" role="status" aria-label="Ollama status">
          <div className="ollama-tab__status-pill">
            <span className="dashboard-rag-status-label">Reachable</span>
            <span className="dashboard-rag-status-value">{running ? 'true' : 'false'}</span>
          </div>
          <div className="ollama-tab__status-pill ollama-tab__status-pill--wide">
            <span className="dashboard-rag-status-label">Base URL</span>
            <span className="dashboard-rag-status-value">{url || '—'}</span>
          </div>
          {statusError ? (
            <div className="ollama-tab__status-pill ollama-tab__status-pill--wide">
              <span className="dashboard-rag-status-label">Error</span>
              <span className="dashboard-rag-status-value">{statusError}</span>
            </div>
          ) : null}
        </div>

        {libraryMsg ? <div className="dashboard-card-error">Library: {libraryMsg}</div> : null}
        {pullErr ? <div className="dashboard-card-error">Pull: {pullErr}</div> : null}
      </section>

      <section className="app-default-card" aria-labelledby="ollama-pull-heading">
        <div className="dashboard-card-header">
          <h2 id="ollama-pull-heading">Pull model</h2>
          <div className="dashboard-card-actions">
            <button
              type="button"
              className="dashboard-primary-btn"
              disabled={pulling}
              onClick={handlePull}
            >
              Pull
            </button>
            {pulling ? (
              <button type="button" className="dashboard-secondary-btn" onClick={cancelPull}>
                Cancel
              </button>
            ) : null}
          </div>
        </div>

        <div className="dashboard-card-actions">
          <input
            type="text"
            className="dashboard-card-field"
            placeholder="Model name (e.g. llama3.2)"
            value={pullName}
            onChange={(e) => setPullName(e.target.value)}
            disabled={pulling}
            aria-label="Model name to pull"
          />
        </div>

        {pullStatus || pullPct != null ? (
          <div className="ollama-tab__pull-progress" aria-label="Pull progress">
            {pullPct != null ? (
              <div className="ollama-tab__progress" aria-hidden="true">
                <div className="ollama-tab__progress-bar" style={{ width: `${pullPct}%` }} />
              </div>
            ) : null}
            <div className="dashboard-card-muted">{pullStatus}</div>
          </div>
        ) : (
          <div className="dashboard-card-muted">
            Pulling runs in the background; progress updates live while this page stays open.
          </div>
        )}
      </section>

      <section className="app-default-card" aria-labelledby="ollama-models-heading">
        <div className="dashboard-card-header">
          <h2 id="ollama-models-heading">Models</h2>
          <div className="dashboard-card-actions">
            <button
              type="button"
              className="dashboard-secondary-btn"
              onClick={refreshLibrary}
              disabled={libraryLoading}
            >
              Refresh list
            </button>
          </div>
        </div>

        {libraryLoading ? (
          <div className="dashboard-card-muted">Loading models…</div>
        ) : sortedModels.length === 0 ? (
          <div className="dashboard-card-muted">No models found. Pull one above.</div>
        ) : (
          <div className="ollama-tab__models-list" role="list" aria-label="Ollama models">
            {(() => {
              const cloudModels = sortedModels.filter((m) => isCloudModelName(m.name));
              const localModels = sortedModels.filter((m) => !isCloudModelName(m.name));
              return (
                <>
                  {cloudModels.length > 0 && (
                    <div className="ollama-tab__models-section">
                      <div className="ollama-tab__models-section-header">
                        <span className="material-symbols-outlined" aria-hidden="true">cloud</span>
                        <span>Cloud Models</span>
                      </div>
                      {cloudModels.map((m) => {
                        const name = m.name || '';
                        const display = parseOllamaModelDisplayParts(name);
                        const cloudModel = true;
                        const familyHint = familyHintByName[name];
                        const brandKey =
                          getOllamaModelBrandKey(name) ||
                          (familyHint ? getOllamaModelBrandKeyFromFamily(familyHint) : null);
                        const brandIconUrl = brandKey ? OLLAMA_BRAND_ICON_URL[brandKey] : null;
                        const busy = rowBusy[name];
                        const hidden = Boolean(m.hidden);
                        const det = expanded[name];
                        const dLoading = detailsLoading[name];
                        return (
                          <div
                            key={name}
                            className={`ollama-tab__model-row${hidden ? ' ollama-tab__model-row--muted' : ''}`}
                            role="listitem"
                          >
                  <div className="ollama-tab__model-row-header">
                    <div className="ollama-tab__model-main">
                      <div className="ollama-tab__model-title">
                        <span
                          className={`ollama-tab__model-cloud-icon material-symbols-outlined${cloudModel ? ' ollama-tab__model-cloud-icon--on' : ''}`}
                          aria-hidden="true"
                          title={cloudModel ? 'Cloud model' : 'Local model'}
                        >
                          {cloudModel ? 'cloud' : 'cloud_off'}
                        </span>
                        {brandIconUrl ? (
                          <img
                            className="ollama-tab__model-brand-icon"
                            src={brandIconUrl}
                            alt=""
                            width={20}
                            height={20}
                            loading="lazy"
                            decoding="async"
                            title={brandKey ? `Provider: ${brandKey}` : undefined}
                          />
                        ) : null}
                        <code title={display.full}>{display.title}</code>
                        {hidden ? (
                          <span className="dashboard-card-muted">Hidden from editors</span>
                        ) : null}
                      </div>
                      <div className="ollama-tab__model-meta">
                        {display.quant && !cloudModel ? (
                          <>
                            <span className="ollama-tab__model-quant">{display.quant}</span>
                            <span className="ollama-tab__dot" aria-hidden="true">
                              ·
                            </span>
                          </>
                        ) : null}
                        {!cloudModel ? (
                          <>
                            <span>{formatBytes(m.size)}</span>
                            <span className="ollama-tab__dot" aria-hidden="true">
                              ·
                            </span>
                          </>
                        ) : null}
                        <span title={m.modified_at ? String(m.modified_at) : undefined}>
                          {formatModifiedAt(m.modified_at)}
                        </span>
                      </div>
                    </div>

                    <div
                      className="ollama-tab__model-menu-root"
                      ref={openMenuModel === name ? modelMenuRootRef : null}
                    >
                      <button
                        type="button"
                        className="ollama-tab__model-menu-trigger"
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
                        <div className="ollama-tab__model-menu" role="menu">
                          <button
                            type="button"
                            className="ollama-tab__model-menu-item"
                            role="menuitem"
                            disabled={busy}
                            onClick={() => {
                              setOpenMenuModel(null);
                              toggleHidden(name, hidden);
                            }}
                          >
                            <span className="material-symbols-outlined" aria-hidden="true">
                              {hidden ? 'visibility' : 'visibility_off'}
                            </span>
                            <span>{hidden ? 'Show in editors' : 'Hide from editors'}</span>
                          </button>
                          <button
                            type="button"
                            className="ollama-tab__model-menu-item"
                            role="menuitem"
                            disabled={busy || dLoading}
                            onClick={() => {
                              setOpenMenuModel(null);
                              toggleDetails(name);
                            }}
                          >
                            <span className="material-symbols-outlined" aria-hidden="true">
                              {det ? 'expand_less' : 'description'}
                            </span>
                            <span>{det ? 'Hide details' : 'Show details'}</span>
                          </button>
                          <button
                            type="button"
                            className="ollama-tab__model-menu-item ollama-tab__model-menu-item--danger"
                            role="menuitem"
                            disabled={busy || pulling}
                            onClick={() => {
                              setOpenMenuModel(null);
                              handleDelete(name);
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

                  {det || dLoading ? (
                    <div className="ollama-tab__details">
                      <div className="ollama-tab__details-header">
                        <span className="ollama-tab__details-title" id={`ollama-details-title-${name}`}>
                          Details
                        </span>
                        <button
                          type="button"
                          className="ollama-tab__details-close"
                          onClick={() => closeDetails(name)}
                          aria-label="Close details"
                        >
                          <span className="material-symbols-outlined" aria-hidden="true">
                            close
                          </span>
                        </button>
                      </div>
                      <div
                        className="ollama-tab__details-body"
                        role="region"
                        aria-labelledby={`ollama-details-title-${name}`}
                      >
                        {dLoading ? (
                          <span className="dashboard-card-muted">Loading…</span>
                        ) : det?.error ? (
                          <span className="dashboard-card-error">{det.error}</span>
                        ) : det ? (
                          <pre>{JSON.stringify(det, null, 2)}</pre>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
                    </div>
                  )}

                  {localModels.length > 0 && (
                    <div className="ollama-tab__models-section">
                      <div className="ollama-tab__models-section-header">
                        <span className="material-symbols-outlined" aria-hidden="true">cloud_off</span>
                        <span>Local Models</span>
                      </div>
                      {localModels.map((m) => {
                        const name = m.name || '';
                        const display = parseOllamaModelDisplayParts(name);
                        const cloudModel = false;
                        const familyHint = familyHintByName[name];
                        const brandKey =
                          getOllamaModelBrandKey(name) ||
                          (familyHint ? getOllamaModelBrandKeyFromFamily(familyHint) : null);
                        const brandIconUrl = brandKey ? OLLAMA_BRAND_ICON_URL[brandKey] : null;
                        const busy = rowBusy[name];
                        const hidden = Boolean(m.hidden);
                        const det = expanded[name];
                        const dLoading = detailsLoading[name];
                        return (
                          <div
                            key={name}
                            className={`ollama-tab__model-row${hidden ? ' ollama-tab__model-row--muted' : ''}`}
                            role="listitem"
                          >
                  <div className="ollama-tab__model-row-header">
                    <div className="ollama-tab__model-main">
                      <div className="ollama-tab__model-title">
                        <span
                          className={`ollama-tab__model-cloud-icon material-symbols-outlined${cloudModel ? ' ollama-tab__model-cloud-icon--on' : ''}`}
                          aria-hidden="true"
                          title={cloudModel ? 'Cloud model' : 'Local model'}
                        >
                          {cloudModel ? 'cloud' : 'cloud_off'}
                        </span>
                        {brandIconUrl ? (
                          <img
                            className="ollama-tab__model-brand-icon"
                            src={brandIconUrl}
                            alt=""
                            width={20}
                            height={20}
                            loading="lazy"
                            decoding="async"
                            title={brandKey ? `Provider: ${brandKey}` : undefined}
                          />
                        ) : null}
                        <code title={display.full}>{display.title}</code>
                        {hidden ? (
                          <span className="dashboard-card-muted">Hidden from editors</span>
                        ) : null}
                      </div>
                      <div className="ollama-tab__model-meta">
                        {display.quant && !cloudModel ? (
                          <>
                            <span className="ollama-tab__model-quant">{display.quant}</span>
                            <span className="ollama-tab__dot" aria-hidden="true">
                              ·
                            </span>
                          </>
                        ) : null}
                        {!cloudModel ? (
                          <>
                            <span>{formatBytes(m.size)}</span>
                            <span className="ollama-tab__dot" aria-hidden="true">
                              ·
                            </span>
                          </>
                        ) : null}
                        <span title={m.modified_at ? String(m.modified_at) : undefined}>
                          {formatModifiedAt(m.modified_at)}
                        </span>
                      </div>
                    </div>

                    <div
                      className="ollama-tab__model-menu-root"
                      ref={openMenuModel === name ? modelMenuRootRef : null}
                    >
                      <button
                        type="button"
                        className="ollama-tab__model-menu-trigger"
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
                        <div className="ollama-tab__model-menu" role="menu">
                          <button
                            type="button"
                            className="ollama-tab__model-menu-item"
                            role="menuitem"
                            disabled={busy}
                            onClick={() => {
                              setOpenMenuModel(null);
                              toggleHidden(name, hidden);
                            }}
                          >
                            <span className="material-symbols-outlined" aria-hidden="true">
                              {hidden ? 'visibility' : 'visibility_off'}
                            </span>
                            <span>{hidden ? 'Show in editors' : 'Hide from editors'}</span>
                          </button>
                          <button
                            type="button"
                            className="ollama-tab__model-menu-item"
                            role="menuitem"
                            disabled={busy || dLoading}
                            onClick={() => {
                              setOpenMenuModel(null);
                              toggleDetails(name);
                            }}
                          >
                            <span className="material-symbols-outlined" aria-hidden="true">
                              {det ? 'expand_less' : 'description'}
                            </span>
                            <span>{det ? 'Hide details' : 'Show details'}</span>
                          </button>
                          <button
                            type="button"
                            className="ollama-tab__model-menu-item ollama-tab__model-menu-item--danger"
                            role="menuitem"
                            disabled={busy || pulling}
                            onClick={() => {
                              setOpenMenuModel(null);
                              handleDelete(name);
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

                  {det || dLoading ? (
                    <div className="ollama-tab__details">
                      <div className="ollama-tab__details-header">
                        <span className="ollama-tab__details-title" id={`ollama-details-title-${name}`}>
                          Details
                        </span>
                        <button
                          type="button"
                          className="ollama-tab__details-close"
                          onClick={() => closeDetails(name)}
                          aria-label="Close details"
                        >
                          <span className="material-symbols-outlined" aria-hidden="true">
                            close
                          </span>
                        </button>
                      </div>
                      <div
                        className="ollama-tab__details-body"
                        role="region"
                        aria-labelledby={`ollama-details-title-${name}`}
                      >
                        {dLoading ? (
                          <span className="dashboard-card-muted">Loading…</span>
                        ) : det?.error ? (
                          <span className="dashboard-card-error">{det.error}</span>
                        ) : det ? (
                          <pre>{JSON.stringify(det, null, 2)}</pre>
                        ) : null}
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}
                    </div>
                  )}
                </>
              );
            })()}
          </div>
        )}
      </section>
    </div>
  );
}

export default OllamaTab;
