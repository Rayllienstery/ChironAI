import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import CoreUIButton from './CoreUIButton';
import CoreUIModal from './CoreUIModal';
import Card from './Card';
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

function extractContentFieldDefaults(content) {
  const next = {};
  const fields = Array.isArray(content?.fields) ? content.fields : [];
  fields.forEach((field) => {
    if (!field?.key) return;
    next[field.key] = field.value ?? '';
  });
  return next;
}

function isRuntimeModelDetailsForModal(details) {
  if (!details || typeof details !== 'object' || Array.isArray(details)) return false;
  return Boolean(String(details.id ?? details.model ?? '').trim());
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

function parseModelName(raw) {
  const s = String(raw ?? '').trim();
  if (!s) return { displayName: s, quantization: '' };
  const lastPart = s.includes('/') ? s.split('/').pop() : s;
  const parts = lastPart.split(':');
  const quantization = parts.length > 1 ? parts.pop() : '';
  let displayName = parts.join(':');
  displayName = displayName.replace(/-GGUF$/i, '');
  return { displayName, quantization };
}

function ExtensionRuntimeTab({ extensionId, title, onErrorStateChange }) {
  const [payload, setPayload] = useState(null);
  const [fieldState, setFieldState] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [lastErrorState, setLastErrorState] = useState(false);
  const [busyActionId, setBusyActionId] = useState('');
  const [busyModelActionKey, setBusyModelActionKey] = useState('');
  const [actionResult, setActionResult] = useState(null);
  const [actionDetails, setActionDetails] = useState(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const onErrorStateChangeRef = useRef(onErrorStateChange);
  useEffect(() => {
    onErrorStateChangeRef.current = onErrorStateChange;
  }, [onErrorStateChange]);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    try {
      const data = await getExtensionTab(extensionId);
      setPayload((prev) => {
        if (JSON.stringify(prev) === JSON.stringify(data)) return prev;
        return data;
      });
      setFieldState((prev) => {
        const next = {
          ...extractFieldDefaults(data?.schema),
          ...extractContentFieldDefaults(data?.content),
          ...prev,
        };
        if (JSON.stringify(prev) === JSON.stringify(next)) return prev;
        return next;
      });
      if (lastErrorState !== false) {
        setLastErrorState(false);
        onErrorStateChangeRef.current?.(false);
      }
    } catch (e) {
      const msg = String(e?.message || e);
      setError(msg);
      if (lastErrorState !== true) {
        setLastErrorState(true);
        onErrorStateChangeRef.current?.(true);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [extensionId, lastErrorState]);

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

  const diagnosticsData = useMemo(() => {
    const schema = payload?.schema;
    const comps = collectSchemaComponents(schema);
    const diag = comps.find((c) => String(c?.type || '').toLowerCase() === 'diagnostics');
    return diag?.value ?? null;
  }, [payload?.schema]);

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
        if (isRuntimeModelDetailsForModal(result.details)) setActionDetails(result.details);
        await load(true);
      } catch (e) {
        setActionResult({ ok: false, message: String(e?.message || e) });
      } finally {
        setBusyActionId('');
      }
    },
    [extensionId, fieldState, load],
  );

  const handleContentAction = useCallback(
    async (action) => {
      const actionId = String(action?.id || action?.action_id || '').trim();
      if (!actionId) return;
      const confirmText = String(action?.confirm || '').trim();
      if (confirmText && !window.confirm(confirmText)) return;
      const payloadKeys = Array.isArray(action?.payload_keys) ? action.payload_keys : [];
      const body = {};
      payloadKeys.forEach((key) => {
        if (typeof key === 'string' && key.trim()) {
          body[key] = fieldState[key] ?? '';
        }
      });
      setBusyActionId(actionId);
      setActionResult(null);
      try {
        const result = await runExtensionTabAction(extensionId, actionId, body);
        setActionResult(result);
        if (actionId === 'refresh') {
          setRefreshKey((prev) => prev + 1);
        }
        const externalUrl = result?.open_external_url || (actionId === 'open_external' ? payload?.content?.open_external_url : '');
        if (externalUrl) window.open(externalUrl, '_blank', 'noopener,noreferrer');
        await load(true);
      } catch (e) {
        setActionResult({ ok: false, message: String(e?.message || e) });
      } finally {
        setBusyActionId('');
      }
    },
    [extensionId, fieldState, load, payload?.content?.open_external_url],
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
      try {
        const result = await runExtensionTabAction(extensionId, actionId, body);
        setActionResult(result);
        if (isRuntimeModelDetailsForModal(result.details)) setActionDetails(result.details);
        await load(true);
      } catch (e) {
        setActionResult({ ok: false, message: String(e?.message || e) });
      } finally {
        setBusyModelActionKey('');
      }
    },
    [extensionId, fieldState, load],
  );

  const renderModelDetailsContent = (model) => {
    if (!model) return null;

    const renderRow = (label, value, key) => (
      <div key={key || label} className="coreui-showcase-data-row" style={{ gridTemplateColumns: '1fr auto' }}>
        <div className="extensions-runtime-model-details-label">{label}</div>
        <div className="extensions-runtime-model-details-value">{value}</div>
      </div>
    );

    const renderSection = (title, data) => {
      if (!data || Object.keys(data).length === 0) return null;
      return (
        <div key={title} className="extensions-runtime-model-details-section">
          <div className="extensions-runtime-model-details-section-title">{title}</div>
          <div className="coreui-showcase-data-table">
            {Object.entries(data).map(([k, v]) => {
              if (v === null || v === undefined || v === '') return null;
              let displayValue = String(v);
              if (k === 'size' || k === 'parameter_size') displayValue = formatBytesLoose(v);
              if (k === 'modified_at') displayValue = formatIsoShort(v);
              return renderRow(k, displayValue, k);
            })}
          </div>
        </div>
      );
    };

    const sections = [];

    // 1. Details (General + Details)
    const details = {};
    ['id', 'model', 'size', 'modified_at', 'digest', 'format'].forEach((k) => {
      if (model[k]) details[k] = model[k];
    });
    if (model.details) Object.assign(details, model.details);
    sections.push(renderSection('Details', details));

    // 2. Model Info
    sections.push(renderSection('Model Info', model.model_info));

    // 3. Capabilities
    if (Array.isArray(model.capabilities) && model.capabilities.length > 0) {
      sections.push(
        <div key="capabilities" className="extensions-runtime-model-details-section">
          <div className="extensions-runtime-model-details-section-title">Capabilities</div>
          <div className="extensions-runtime-model-details-value--array">
            {model.capabilities.map((cap) => (
              <span key={cap} className="extensions-runtime-model-details-tag">
                {cap}
              </span>
            ))}
          </div>
        </div>,
      );
    }

    return <div className="extensions-runtime-model-details">{sections}</div>;
  };

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
        const cloudModels = rows
          .filter((r) => String(r?.id ?? r?.model ?? '').toLowerCase().endsWith('cloud'))
          .sort((a, b) => {
            const nameA = String(a?.id ?? a?.model ?? '').toLowerCase();
            const nameB = String(b?.id ?? b?.model ?? '').toLowerCase();
            return nameA.localeCompare(nameB);
          });

        const localModels = rows
          .filter((r) => !String(r?.id ?? r?.model ?? '').toLowerCase().endsWith('cloud'))
          .sort((a, b) => {
            const nameA = String(a?.id ?? a?.model ?? '').toLowerCase();
            const nameB = String(b?.id ?? b?.model ?? '').toLowerCase();
            return nameA.localeCompare(nameB);
          });

        const renderModelCard = (row, index) => {
          const modelId = String(row?.id ?? row?.model ?? '').trim();
          const { displayName, quantization } = parseModelName(modelId);
          const sizeText = formatBytesLoose(row?.size);
          const modifiedText = formatIsoShort(row?.modified_at);

          const modelInfo = row?.model_info;
          const contextLengthKey = modelInfo && typeof modelInfo === 'object'
            ? Object.keys(modelInfo).find((k) => k.endsWith('context_length'))
            : null;
          const contextLength = contextLengthKey ? modelInfo[contextLengthKey] : null;

          const capabilities = Array.isArray(row?.capabilities) ? row.capabilities : [];

          const showTpl = modelActionTemplates.show;

          return (
            <Card
              key={`${key}-model-${modelId || index}`}
              className="extensions-runtime-model-card"
              interactive={Boolean(modelId && showTpl)}
              elevateOnHover={Boolean(modelId && showTpl)}
              onClick={() => {
                if (modelId && showTpl) {
                  void runModelMenuAction(showTpl, modelId);
                }
              }}
            >
              <div className="extensions-runtime-model-card__top">
                <div className="extensions-runtime-model-card__title-wrap">
                  <div className="extensions-runtime-model-card__title" title={modelId || '—'}>
                    {displayName || modelId || '—'}
                  </div>
                  {quantization ? (
                    <div className="extensions-runtime-model-card__quant">
                      <span className="extensions-runtime-model-meta-k">Quantization:</span>
                      <span className="extensions-runtime-model-meta-v">{quantization}</span>
                    </div>
                  ) : null}
                  {contextLength != null ? (
                    <div className="extensions-runtime-model-card__quant">
                      <span className="extensions-runtime-model-meta-k">Context:</span>
                      <span className="extensions-runtime-model-meta-v">{Number(contextLength).toLocaleString()}</span>
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
                {modifiedText && (
                  <div className="extensions-runtime-model-meta-row">
                    <span className="extensions-runtime-model-meta-k">Modified:</span>
                    <span className="extensions-runtime-model-meta-v">{modifiedText}</span>
                  </div>
                )}
                {capabilities.length > 0 ? (
                  <div className="extensions-runtime-model-card__caps">
                    {capabilities.map((cap) => (
                      <span key={cap} className="extensions-runtime-model-card__cap-tag">{cap}</span>
                    ))}
                  </div>
                ) : null}
              </div>
            </Card>
          );
        };

        return (
          <div key={key} className="extensions-runtime-item">
            <div className="extensions-runtime-label">{component.label || 'Installed models'}</div>
            {rows.length === 0 ? (
              <div className="extensions-runtime-text">No models.</div>
            ) : (
              <>
                {cloudModels.length > 0 && (
                  <>
                    <div className="extensions-runtime-label--large">
                      <span className="material-symbols-outlined">cloud</span>
                      Cloud
                    </div>
                    <div className="extensions-runtime-model-grid">
                      {cloudModels.map((row, index) => renderModelCard(row, index))}
                    </div>
                  </>
                )}
                {localModels.length > 0 && (
                  <>
                    <div className="extensions-runtime-label--large">
                      <span className="material-symbols-outlined">cloud_off</span>
                      Local
                    </div>
                    <div className="extensions-runtime-model-grid">
                      {localModels.map((row, index) => renderModelCard(row, index))}
                    </div>
                  </>
                )}
              </>
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
      <div className="settings-tab settings-tab--fullwidth tab-view">
        <section className="app-default-card llm-proxy-section-gap">
          <div className="dashboard-card-error" role="alert">
            {error}
          </div>
        </section>
      </div>
    );
  }

  const content = payload?.content;
  const isIframeContent = content?.type === 'iframe';
  const contentFields = Array.isArray(content?.fields) ? content.fields : [];
  const contentActions = Array.isArray(content?.actions) ? content.actions : [];
  const contentDetails = Array.isArray(content?.details) ? content.details : [];
  const contentStatus = payload?.status && typeof payload.status === 'object' ? payload.status : null;

  return (
    <div className="settings-tab settings-tab--fullwidth tab-view">

      {actionResult && (
        <div
          className={actionResult.ok === false ? 'dashboard-card-error llm-proxy-section-gap-sm' : 'dashboard-card-muted llm-proxy-section-gap-sm'}
          role={actionResult.ok === false ? 'alert' : 'status'}
        >
          {actionResult.message || 'Action completed'}
        </div>
      )}

      {isIframeContent ? (
        <section className="app-default-card llm-proxy-section-gap extensions-runtime-frame-shell">
          <div className="dashboard-card-header extensions-runtime-frame-header">
            <div>
              <h2>{content.title || payload?.title || title || extensionId}</h2>
              {contentStatus ? (
                <div className="extensions-runtime-frame-status">
                  <span
                    className={`extensions-runtime-frame-status__dot ${contentStatus.running ? 'running' : contentStatus.tone === 'error' ? 'error' : 'stopped'}`}
                    aria-hidden="true"
                  />
                  <span>{contentStatus.message || (contentStatus.running ? 'running' : 'stopped')}</span>
                  {contentStatus.http_status != null ? <span>HTTP {contentStatus.http_status}</span> : null}
                </div>
              ) : null}
            </div>
            <div className="dashboard-card-actions extensions-runtime-frame-actions">
              {contentActions.map((action) => {
                const actionId = String(action?.id || action?.action_id || '');
                return (
                  <CoreUIButton
                    key={actionId || action.label}
                    variant={action.variant === 'danger' ? 'danger' : action.variant === 'primary' ? 'primary' : 'default'}
                    onClick={() => void handleContentAction(action)}
                    disabled={Boolean(action.disabled) || busyActionId === actionId}
                  >
                    {busyActionId === actionId ? 'Working...' : action.label || actionId}
                  </CoreUIButton>
                );
              })}
            </div>
          </div>

          {contentFields.length ? (
            <div className="extensions-runtime-frame-fields">
              {contentFields.map((field) => {
                const key = String(field.key || '');
                return (
                  <label key={key} className="extensions-runtime-frame-field">
                    <span>{field.label || key}</span>
                    <input
                      type={field.secret ? 'password' : 'text'}
                      value={fieldState[key] ?? ''}
                      placeholder={field.placeholder || ''}
                      onChange={(e) => setFieldState((prev) => ({ ...prev, [key]: e.target.value }))}
                    />
                  </label>
                );
              })}
            </div>
          ) : null}

          {contentDetails.length ? (
            <div className="extensions-runtime-frame-details">
              {contentDetails.map((item) => (
                <div key={`${item.label}:${item.value}`} className="extensions-runtime-frame-detail">
                  <span>{item.label}</span>
                  <strong>{item.value || '-'}</strong>
                </div>
              ))}
            </div>
          ) : null}

          <div className="extensions-runtime-frame-wrap">
            <iframe
              key={refreshKey}
              className="extensions-runtime-frame"
              title={content.title || payload?.title || title || extensionId}
              src={content.src || 'about:blank'}
              allow="clipboard-read; clipboard-write"
            />
          </div>
        </section>
      ) : null}

      {diagnosticsData ? (() => {
        const h = diagnosticsData.health;
        const healthOk = h?.ok === true;
        const healthStatus = h?.status || 'unknown';
        const serviceBusy = busyActionId === 'start_service' || busyActionId === 'stop_service';
        return (
          <section className="app-default-card llm-proxy-section-gap">
            <div className="dashboard-card-header">
              <h2>Runtime details</h2>
            </div>
            <div className="extensions-runtime-diagnostics-cards">
              <Card className="extensions-runtime-diag-card">
                <div className="extensions-runtime-diag-card__label">Health</div>
                <div className={`extensions-runtime-diag-card__value extensions-runtime-diag-card__value--${healthOk ? 'ok' : 'error'}`}>
                  <span className="extensions-runtime-diag-card__dot" />
                  {healthStatus}
                </div>
              </Card>
              <Card className="extensions-runtime-diag-card">
                <div className="extensions-runtime-diag-card__label">Models</div>
                <div className="extensions-runtime-diag-card__value">
                  {diagnosticsData.visible_models ?? '?'} / {diagnosticsData.total_models ?? '?'}
                </div>
              </Card>
              <Card className="extensions-runtime-diag-card">
                <div className="extensions-runtime-diag-card__label">Base URL</div>
                <div className="extensions-runtime-diag-card__value extensions-runtime-diag-card__value--mono">
                  {diagnosticsData.base_url || '—'}
                </div>
              </Card>
              <Card className="extensions-runtime-diag-card">
                <div className="extensions-runtime-diag-card__label">Chat URL</div>
                <div className="extensions-runtime-diag-card__value extensions-runtime-diag-card__value--mono">
                  {diagnosticsData.chat_url || '—'}
                </div>
              </Card>
            </div>
            <div className="extensions-runtime-diagnostics-actions">
              <CoreUIButton
                variant={healthOk ? 'danger' : 'primary'}
                disabled={serviceBusy}
                onClick={async () => {
                  const actionId = healthOk ? 'stop_service' : 'start_service';
                  if (actionId === 'stop_service' && !window.confirm('Stop the Ollama service?')) return;
                  setBusyActionId(actionId);
                  try {
                    const result = await runExtensionTabAction(extensionId, actionId, {});
                    setActionResult(result);
                    await load(true);
                  } catch (e) {
                    setActionResult({ ok: false, message: String(e?.message || e) });
                  } finally {
                    setBusyActionId('');
                  }
                }}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  {healthOk ? 'stop' : 'play_arrow'}
                </span>
                {serviceBusy ? 'Working…' : healthOk ? 'Stop Ollama' : 'Start Ollama'}
              </CoreUIButton>
              <CoreUIButton
                variant="secondary"
                onClick={async () => {
                  setBusyActionId('refresh');
                  try {
                    await runExtensionTabAction(extensionId, 'refresh', {});
                    setRefreshKey((prev) => prev + 1);
                    await load();
                  } catch (e) {
                    setActionResult({ ok: false, message: String(e?.message || e) });
                  } finally {
                    setBusyActionId('');
                  }
                }}
                disabled={busyActionId === 'refresh'}
              >
                <span className="material-symbols-outlined" aria-hidden="true">refresh</span>
                {busyActionId === 'refresh' ? 'Working…' : 'Refresh'}
              </CoreUIButton>
            </div>
          </section>
        );
      })() : null}

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

      {actionDetails && (() => {
        const modelId = String(actionDetails?.id ?? actionDetails?.model ?? '').trim();
        const hiddenRaw = String(actionDetails?.hidden ?? '').trim().toLowerCase();
        const isHidden = hiddenRaw === 'yes' || hiddenRaw === 'true' || hiddenRaw === '1';

        const hideTpl = modelActionTemplates.hide;
        const unhideTpl = modelActionTemplates.unhide;
        const delTpl = modelActionTemplates.delete;

        const busyHide = busyModelActionKey === `hide_model:${modelId}`;
        const busyUnhide = busyModelActionKey === `unhide_model:${modelId}`;
        const busyDel = busyModelActionKey === `delete_model:${modelId}`;

        return (
          <CoreUIModal
            title="Model Details"
            onClose={() => setActionDetails(null)}
            footer={
              <div className="extensions-runtime-model-details-actions">
                {isHidden ? (
                  unhideTpl ? (
                    <CoreUIButton
                      variant="primary"
                      onClick={() => void runModelMenuAction(unhideTpl, modelId)}
                      disabled={busyUnhide || Boolean(busyActionId)}
                    >
                      <span className="material-symbols-outlined" aria-hidden="true">visibility</span>
                      {busyUnhide ? 'Working…' : 'Unhide model'}
                    </CoreUIButton>
                  ) : null
                ) : (
                  hideTpl ? (
                    <CoreUIButton
                      variant="primary"
                      onClick={() => void runModelMenuAction(hideTpl, modelId)}
                      disabled={busyHide || Boolean(busyActionId)}
                    >
                      <span className="material-symbols-outlined" aria-hidden="true">visibility_off</span>
                      {busyHide ? 'Working…' : 'Hide model'}
                    </CoreUIButton>
                  ) : null
                )}
                {delTpl ? (
                  <CoreUIButton
                    variant="danger"
                    onClick={async () => {
                      const actionId = String(delTpl?.action_id || '').trim();
                      if (!actionId) return;
                      const confirmText = String(delTpl?.confirm || '').trim();
                      if (confirmText && !window.confirm(confirmText)) return;
                      const busyKey = `delete_model:${modelId}`;
                      setBusyModelActionKey(busyKey);
                      try {
                        const result = await runExtensionTabAction(extensionId, actionId, { selected_model: modelId });
                        setActionResult(result);
                        if (result?.ok !== false) {
                          setActionDetails(null);
                          await load();
                        }
                      } catch (e) {
                        setActionResult({ ok: false, message: String(e?.message || e) });
                      } finally {
                        setBusyModelActionKey('');
                      }
                    }}
                    disabled={busyDel || Boolean(busyActionId)}
                  >
                    <span className="material-symbols-outlined" aria-hidden="true">delete</span>
                    {busyDel ? 'Working…' : 'Delete model'}
                  </CoreUIButton>
                ) : null}
              </div>
            }
          >
            {renderModelDetailsContent(actionDetails)}
          </CoreUIModal>
        );
      })()}
    </div>
  );
}

export default ExtensionRuntimeTab;
