import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import CoreUIButton from './CoreUIButton';
import { getExtensionTab, runExtensionTabAction } from '../services/api';
import '../styles/components/ExtensionRuntimeTab.css';
import { getOllamaModelBrandKey, OLLAMA_BRAND_ICON_URL } from '../utils/ollamaModelBrandIcons';

function extractFieldDefaults(schema) {
  const next = {};
  const pages = Array.isArray(schema?.pages) ? schema.pages : [];
  pages.forEach((page) => {
    const sections = Array.isArray(page?.sections) ? page.sections : [];
    sections.forEach((section) => {
      const components = Array.isArray(section?.components) ? section.components : [];
      components.forEach((component) => {
        if (!component?.key) return;
        if (component.type === 'input' || component.type === 'select') {
          next[component.key] = component.value ?? '';
        }
      });
    });
  });
  return next;
}

function collectSchemaComponents(schema) {
  const out = [];
  const pages = Array.isArray(schema?.pages) ? schema.pages : [];
  pages.forEach((page) => {
    const sections = Array.isArray(page?.sections) ? page.sections : [];
    sections.forEach((section) => {
      const components = Array.isArray(section?.components) ? section.components : [];
      components.forEach((c) => out.push(c));
    });
  });
  return out;
}

function formatBytesLoose(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return '';
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return raw;
  const gb = n / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(2)} GB`;
  const mb = n / 1024 ** 2;
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  const kb = n / 1024;
  if (kb >= 1) return `${kb.toFixed(0)} KB`;
  return `${n} B`;
}

function formatIsoShort(value) {
  const raw = String(value ?? '').trim();
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString();
}

function ExtensionRuntimeTab({ extensionId, title, onErrorStateChange }) {
  const [payload, setPayload] = useState(null);
  const [fieldState, setFieldState] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyActionId, setBusyActionId] = useState('');
  const [busyModelActionKey, setBusyModelActionKey] = useState('');
  const [actionResult, setActionResult] = useState(null);
  const [openModelMenuId, setOpenModelMenuId] = useState('');

  const onErrorStateChangeRef = useRef(onErrorStateChange);
  useEffect(() => {
    onErrorStateChangeRef.current = onErrorStateChange;
  }, [onErrorStateChange]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getExtensionTab(extensionId);
      setPayload(data);
      setFieldState((prev) => ({ ...extractFieldDefaults(data?.schema), ...prev }));
      onErrorStateChangeRef.current?.(false);
    } catch (e) {
      const msg = String(e?.message || e);
      setError(msg);
      onErrorStateChangeRef.current?.(true);
    } finally {
      setLoading(false);
    }
  }, [extensionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const pages = useMemo(
    () => (Array.isArray(payload?.schema?.pages) ? payload.schema.pages : []),
    [payload],
  );

  const modelActionTemplates = useMemo(() => {
    const schema = payload?.schema;
    const comps = collectSchemaComponents(schema);
    const pick = (id) => comps.find((c) => String(c?.type || '').toLowerCase() === 'action' && String(c?.action_id || '') === id);
    return {
      show: pick('show_model'),
      hide: pick('hide_model'),
      unhide: pick('unhide_model'),
      delete: pick('delete_model'),
    };
  }, [payload?.schema]);

  useEffect(() => {
    if (!openModelMenuId) return;
    const onDown = (e) => {
      const t = e.target;
      if (!(t instanceof Element)) return;
      if (t.closest?.('[data-extensions-runtime-model-menu-root="1"]')) return;
      setOpenModelMenuId('');
    };
    window.addEventListener('mousedown', onDown, true);
    return () => window.removeEventListener('mousedown', onDown, true);
  }, [openModelMenuId]);

  const handleAction = useCallback(
    async (component) => {
      const actionId = String(component?.action_id || '').trim();
      if (!actionId) return;
      const confirmText = String(component?.confirm || '').trim();
      if (confirmText && !window.confirm(confirmText)) return;
      const payloadKeys = Array.isArray(component?.payload_keys) ? component.payload_keys : [];
      const actionPayload = {};
      payloadKeys.forEach((key) => {
        if (typeof key === 'string' && key.trim()) {
          actionPayload[key] = fieldState[key] ?? '';
        }
      });
      setBusyActionId(actionId);
      setActionResult(null);
      try {
        const result = await runExtensionTabAction(extensionId, actionId, actionPayload);
        setActionResult(result);
        await load();
      } catch (e) {
        setActionResult({ ok: false, message: String(e?.message || e) });
      } finally {
        setBusyActionId('');
      }
    },
    [extensionId, fieldState, load],
  );

  const runModelMenuAction = useCallback(
    async (template, modelId) => {
      const actionId = String(template?.action_id || '').trim();
      if (!actionId) return;
      const confirmText = String(template?.confirm || '').trim();
      if (confirmText && !window.confirm(confirmText)) return;
      const payloadKeys = Array.isArray(template?.payload_keys) ? template.payload_keys : [];
      const body = {};
      payloadKeys.forEach((k) => {
        if (typeof k === 'string' && k.trim()) {
          if (k === 'selected_model') body[k] = modelId;
          else body[k] = fieldState[k] ?? '';
        }
      });
      const busyKey = `${actionId}:${modelId}`;
      setBusyModelActionKey(busyKey);
      setOpenModelMenuId('');
      try {
        const result = await runExtensionTabAction(extensionId, actionId, body);
        setActionResult(result);
        await load();
      } catch (e) {
        setActionResult({ ok: false, message: String(e?.message || e) });
      } finally {
        setBusyModelActionKey('');
      }
    },
    [extensionId, fieldState, load],
  );

  const renderComponent = (component) => {
    const key = String(component?.key || component?.action_id || Math.random());
    if (component?.type === 'status') {
      const status = String(component.status || 'unknown');
      return (
        <div key={key} className="extensions-runtime-item">
          <div className="extensions-runtime-label">{component.label || 'Status'}</div>
          <div className={`extensions-runtime-status extensions-runtime-status--${status}`}>
            <strong>{status}</strong>
            {component.message ? (
              <>
                {' '}
                <span>{component.message}</span>
              </>
            ) : null}
          </div>
        </div>
      );
    }
    if (component?.type === 'text') {
      return (
        <div key={key} className="extensions-runtime-item">
          <div className="extensions-runtime-label">{component.label || key}</div>
          <div className="extensions-runtime-text">{component.value ?? '—'}</div>
        </div>
      );
    }
    if (component?.type === 'input') {
      return (
        <label key={key} className="extensions-runtime-item">
          <div className="extensions-runtime-label">{component.label || key}</div>
          <input
            type={component.secret ? 'password' : 'text'}
            value={fieldState[key] ?? ''}
            placeholder={component.placeholder || ''}
            onChange={(e) => setFieldState((prev) => ({ ...prev, [key]: e.target.value }))}
          />
        </label>
      );
    }
    if (component?.type === 'select') {
      const options = Array.isArray(component.options) ? component.options : [];
      return (
        <label key={key} className="extensions-runtime-item">
          <div className="extensions-runtime-label">{component.label || key}</div>
          <select
            value={fieldState[key] ?? component.value ?? ''}
            onChange={(e) => setFieldState((prev) => ({ ...prev, [key]: e.target.value }))}
          >
            {options.map((option) => (
              <option key={`${key}-${option.value}`} value={option.value}>
                {option.label || option.value}
              </option>
            ))}
          </select>
        </label>
      );
    }
    if (component?.type === 'action') {
      const actionId = String(component.action_id || '');
      return (
        <div key={key} className="extensions-runtime-item extensions-runtime-item--action">
          <CoreUIButton
            variant={component.variant === 'danger' ? 'secondary' : 'primary'}
            onClick={() => void handleAction(component)}
            disabled={Boolean(component.disabled) || busyActionId === actionId}
          >
            {busyActionId === actionId ? 'Working...' : component.label || actionId}
          </CoreUIButton>
        </div>
      );
    }
    if (component?.type === 'table') {
      const columns = Array.isArray(component.columns) ? component.columns : [];
      const rows = Array.isArray(component.rows) ? component.rows : [];

      if (key === 'provider_models') {
        return (
          <div key={key} className="extensions-runtime-item">
            <div className="extensions-runtime-label">{component.label || 'Installed models'}</div>
            {rows.length === 0 ? (
              <div className="extensions-runtime-text">No models.</div>
            ) : (
              <div className="extensions-runtime-model-grid" data-extensions-runtime-model-menu-root="1">
                {rows.map((row, index) => {
                  const modelId = String(row?.id ?? row?.model ?? '').trim();
                  const sizeText = formatBytesLoose(row?.size);
                  const modifiedText = formatIsoShort(row?.modified_at);
                  const hiddenRaw = String(row?.hidden ?? '').trim().toLowerCase();
                  const isHidden = hiddenRaw === 'yes' || hiddenRaw === 'true' || hiddenRaw === '1';
                  const menuOpen = openModelMenuId === modelId;

                  const showTpl = modelActionTemplates.show;
                  const hideTpl = modelActionTemplates.hide;
                  const unhideTpl = modelActionTemplates.unhide;
                  const delTpl = modelActionTemplates.delete;

                  const busyShow = busyModelActionKey === `show_model:${modelId}`;
                  const busyHide = busyModelActionKey === `hide_model:${modelId}`;
                  const busyUnhide = busyModelActionKey === `unhide_model:${modelId}`;
                  const busyDel = busyModelActionKey === `delete_model:${modelId}`;

                  return (
                    <div key={`${key}-model-${modelId || index}`} className="extensions-runtime-model-card">
                      <div className="extensions-runtime-model-card__top">
                        <div className="extensions-runtime-model-card__title-wrap">
                          <span className="material-symbols-outlined extensions-runtime-model-cloud-icon">
                            {modelId.toLowerCase().endsWith('cloud') ? 'cloud' : 'cloud_off'}
                          </span>
                          <div className="extensions-runtime-model-card__title" title={modelId || '—'}>
                            {modelId || '—'}
                          </div>
                        </div>
                        <div className="extensions-runtime-model-card__menu">
                          <button
                            type="button"
                            className="extensions-runtime-model-menu-btn"
                            aria-haspopup="menu"
                            aria-expanded={menuOpen ? 'true' : 'false'}
                            aria-label="Model actions"
                            onClick={() => setOpenModelMenuId((cur) => (cur === modelId ? '' : modelId))}
                            disabled={!modelId}
                          >
                            <span className="material-symbols-outlined" aria-hidden="true">
                              more_vert
                            </span>
                          </button>
                          {menuOpen ? (
                            <div className="extensions-runtime-model-menu" role="menu">
                              {showTpl ? (
                                <button
                                  type="button"
                                  className="extensions-runtime-model-menu-item"
                                  role="menuitem"
                                  disabled={!modelId || busyShow || Boolean(busyActionId)}
                                  onClick={() => void runModelMenuAction(showTpl, modelId)}
                                >
                                  {busyShow ? 'Working…' : 'Show details'}
                                </button>
                              ) : null}
                              {hideTpl ? (
                                <button
                                  type="button"
                                  className="extensions-runtime-model-menu-item"
                                  role="menuitem"
                                  disabled={!modelId || isHidden || busyHide || Boolean(busyActionId)}
                                  onClick={() => void runModelMenuAction(hideTpl, modelId)}
                                >
                                  {busyHide ? 'Working…' : 'Hide model'}
                                </button>
                              ) : null}
                              {unhideTpl ? (
                                <button
                                  type="button"
                                  className="extensions-runtime-model-menu-item"
                                  role="menuitem"
                                  disabled={!modelId || !isHidden || busyUnhide || Boolean(busyActionId)}
                                  onClick={() => void runModelMenuAction(unhideTpl, modelId)}
                                >
                                  {busyUnhide ? 'Working…' : 'Unhide model'}
                                </button>
                              ) : null}
                              {delTpl ? (
                                <button
                                  type="button"
                                  className="extensions-runtime-model-menu-item extensions-runtime-model-menu-item--danger"
                                  role="menuitem"
                                  disabled={!modelId || busyDel || Boolean(busyActionId)}
                                  onClick={() => void runModelMenuAction(delTpl, modelId)}
                                >
                                  {busyDel ? 'Working…' : 'Delete model'}
                                </button>
                              ) : null}
                            </div>
                          ) : null}
                        </div>
                      </div>

                      <div className="extensions-runtime-model-card__provider">
                        <span className="extensions-runtime-model-meta-k">Provider:</span>
                        {(() => {
                          const brandKey = getOllamaModelBrandKey(modelId);
                          const iconUrl = brandKey ? OLLAMA_BRAND_ICON_URL[brandKey] : null;
                          return (
                            <div className="extensions-runtime-model-provider-val">
                              {iconUrl && (
                                <img
                                  src={iconUrl}
                                  alt=""
                                  className="extensions-runtime-model-provider-icon"
                                />
                              )}
                              <span className="extensions-runtime-model-meta-v">{brandKey || 'unknown'}</span>
                            </div>
                          );
                        })()}
                      </div>

                      <div className="extensions-runtime-model-card__meta">
                        {sizeText && !modelId.toLowerCase().endsWith('cloud') ? (
                          <div className="extensions-runtime-model-meta-row">
                            <span className="extensions-runtime-model-meta-k">Size:</span>
                            <span className="extensions-runtime-model-meta-v">{sizeText}</span>
                          </div>
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        );
      }

      return (
        <div key={key} className="extensions-runtime-item">
          <div className="extensions-runtime-label">{component.label || key}</div>
          {rows.length === 0 ? (
            <div className="extensions-runtime-text">No rows.</div>
          ) : (
            <div className="extensions-runtime-table-wrap">
              <table className="collections-table">
                <thead>
                  <tr>
                    {columns.map((column) => (
                      <th key={`${key}-${column.key}`}>{column.label || column.key}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr key={`${key}-row-${index}`}>
                      {columns.map((column) => (
                        <td key={`${key}-${index}-${column.key}`}>{row?.[column.key] ?? '—'}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      );
    }
    if (component?.type === 'diagnostics') {
      return (
        <div key={key} className="extensions-runtime-item">
          <div className="extensions-runtime-label">{component.label || key}</div>
          <pre className="extensions-runtime-diagnostics">
            {JSON.stringify(component.value ?? {}, null, 2)}
          </pre>
        </div>
      );
    }
    return null;
  };

  if (loading) {
    return <div className="loading">Loading {title || extensionId}...</div>;
  }

  if (error) {
    return (
      <div className="settings-tab settings-tab--fullwidth">
        <section className="app-default-card llm-proxy-section-gap">
          <div className="dashboard-card-error" role="alert">
            {error}
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="settings-tab settings-tab--fullwidth">
      <section className="app-default-card llm-proxy-section-gap">
        <div className="dashboard-card-actions">
          <CoreUIButton variant="primary" onClick={() => void load()}>
            Refresh
          </CoreUIButton>
        </div>
      </section>

      {actionResult && (
        <div
          className={actionResult.ok === false ? 'dashboard-card-error llm-proxy-section-gap-sm' : 'dashboard-card-muted llm-proxy-section-gap-sm'}
          role={actionResult.ok === false ? 'alert' : 'status'}
        >
          {actionResult.message || 'Action completed'}
          {actionResult.details ? (
            <pre className="extensions-runtime-diagnostics">
              {JSON.stringify(actionResult.details, null, 2)}
            </pre>
          ) : null}
        </div>
      )}

      {pages.map((page) => (
        <div key={page.id || 'page'}>
          {(Array.isArray(page.sections) ? page.sections : []).map((section) => (
            <section key={section.id || section.title} className="app-default-card llm-proxy-section-gap">
              <div className="dashboard-card-header">
                <h2>{section.title || 'Section'}</h2>
              </div>
              <div className="extensions-runtime-section">
                {(Array.isArray(section.components) ? section.components : []).map(renderComponent)}
              </div>
            </section>
          ))}
        </div>
      ))}
    </div>
  );
}

export default ExtensionRuntimeTab;
