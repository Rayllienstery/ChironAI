import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import CoreUIButton from './CoreUIButton';
import CoreUIDockerCard from './CoreUIDockerCard';
import CoreUIModal from './CoreUIModal';
import Card from './Card';
import { useOptionalNotificationCenter } from './NotificationCenterContext';
import { getExtensionTab, runExtensionTabAction } from '../services/api';
import { formatElapsedMs } from '../utils/elapsedTime';
import '../styles/components/ExtensionRuntimeTab.css';

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
  return Boolean(
    String(details.id ?? details.model ?? details.name ?? '').trim()
    || details.details
    || details.model_info
    || details.capabilities
    || details.modelfile
  );
}

function normalizeModelDetailsForModal(details, modelId = '') {
  const src = details && typeof details === 'object' && !Array.isArray(details) ? details : {};
  const id = String(src.id ?? src.model ?? src.name ?? modelId ?? '').trim();
  return {
    ...src,
    id: String(src.id ?? id).trim(),
    model: String(src.model ?? id).trim(),
  };
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

function serviceActionIcon(actionId) {
  switch (String(actionId || '')) {
    case 'refresh':
      return 'refresh';
    case 'start':
    case 'start_service':
      return 'play_arrow';
    case 'stop':
    case 'stop_service':
      return 'stop';
    case 'clear_backend':
      return 'backspace';
    case 'open_external':
      return 'open_in_new';
    default:
      return '';
  }
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

function isRuntimeStillLoadingMessage(message) {
  return String(message || '').toLowerCase().includes('extension runtime is still loading');
}

function serviceActionTimeoutMs(actionId) {
  return actionId === 'start_service' || actionId === 'stop_service' ? 30 * 60 * 1000 : 30_000;
}

function actionLabel(action, actionId) {
  return String(action?.label || action?.title || actionId || 'Action').trim();
}

function ExtensionActionLiveNotification({ action, nowMs }) {
  if (!action) return null;
  const elapsedMs = Math.max(0, nowMs - action.startedAt);
  return (
    <div className="extensions-runtime-action-live">
      <div className="extensions-runtime-action-live__row">
        <span className="extensions-runtime-action-live__label">Action</span>
        <span className="extensions-runtime-action-live__value">{action.label}</span>
      </div>
      <div className="extensions-runtime-action-live__row">
        <span className="extensions-runtime-action-live__label">Elapsed</span>
        <span className="extensions-runtime-action-live__timer">{formatElapsedMs(elapsedMs)}</span>
      </div>
    </div>
  );
}

function ActionElapsedChip({ action, nowMs }) {
  if (!action) return null;
  return (
    <span className="extensions-runtime-action-timer" aria-label={`Elapsed ${formatElapsedMs(nowMs - action.startedAt)}`}>
      <span className="material-symbols-outlined" aria-hidden="true">timer</span>
      {formatElapsedMs(nowMs - action.startedAt)}
    </span>
  );
}

function ExtensionRuntimeTab({ extensionId, title, onErrorStateChange }) {
  const notificationCenter = useOptionalNotificationCenter();
  const setExtensionLiveActivity = notificationCenter?.setLiveActivity;
  const clearExtensionLiveActivity = notificationCenter?.clearLiveActivity;
  const persistExtensionNotification = notificationCenter?.persistNotification;
  const [payload, setPayload] = useState(null);
  const [fieldState, setFieldState] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [runtimeLoadingMessage, setRuntimeLoadingMessage] = useState('');
  const [lastErrorState, setLastErrorState] = useState(false);
  const [busyActionId, setBusyActionId] = useState('');
  const [busyModelActionKey, setBusyModelActionKey] = useState('');
  const [actionResult, setActionResult] = useState(null);
  const [actionDetails, setActionDetails] = useState(null);
  const [activeAction, setActiveAction] = useState(null);
  const [actionTimerNow, setActionTimerNow] = useState(Date.now());
  const [refreshKey, setRefreshKey] = useState(0);
  const [openModelMenuId, setOpenModelMenuId] = useState('');
  const [openModelMenuPos, setOpenModelMenuPos] = useState(null);

  const onErrorStateChangeRef = useRef(onErrorStateChange);
  useEffect(() => {
    onErrorStateChangeRef.current = onErrorStateChange;
  }, [onErrorStateChange]);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    setError(null);
    setRuntimeLoadingMessage('');
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
      const nextState = isRuntimeStillLoadingMessage(msg) ? 'loading' : true;
      if (nextState === 'loading') {
        setRuntimeLoadingMessage(msg);
      } else {
        setError(msg);
      }
      if (lastErrorState !== nextState) {
        setLastErrorState(nextState);
        onErrorStateChangeRef.current?.(nextState);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [extensionId, lastErrorState]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (!activeAction) return undefined;
    setActionTimerNow(Date.now());
    const id = setInterval(() => setActionTimerNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [activeAction]);

  const activeActionLiveId = activeAction
    ? `extension-action:${extensionId}:${activeAction.startedAt}:${activeAction.id}`
    : '';

  useEffect(() => {
    if (!clearExtensionLiveActivity || !activeActionLiveId) return undefined;
    return () => clearExtensionLiveActivity(activeActionLiveId);
  }, [activeActionLiveId, clearExtensionLiveActivity]);

  useEffect(() => {
    if (!setExtensionLiveActivity || !activeAction || !activeActionLiveId) return;
    setExtensionLiveActivity(
      activeActionLiveId,
      'extensions',
      <ExtensionActionLiveNotification action={activeAction} nowMs={actionTimerNow} />,
      { headerLeading: <span className="notification-center-card-spinner" aria-hidden="true" /> },
    );
  }, [activeAction, activeActionLiveId, actionTimerNow, setExtensionLiveActivity]);

  // Auto-retry while runtime is still bootstrapping.
  useEffect(() => {
    if (!runtimeLoadingMessage) return undefined;
    const id = setInterval(() => {
      void load(true);
    }, 2000);
    return () => clearInterval(id);
  }, [runtimeLoadingMessage, load]);

  useEffect(() => {
    if (!openModelMenuId) return undefined;
    const onDown = (e) => {
      const t = e.target;
      if (!(t instanceof Element)) return;
      if (t.closest?.('[data-extensions-runtime-model-menu-root="1"]')) return;
      setOpenModelMenuId('');
      setOpenModelMenuPos(null);
    };
    const onScroll = () => {
      setOpenModelMenuId('');
      setOpenModelMenuPos(null);
    };
    window.addEventListener('mousedown', onDown, true);
    window.addEventListener('scroll', onScroll, true);
    return () => {
      window.removeEventListener('mousedown', onDown, true);
      window.removeEventListener('scroll', onScroll, true);
    };
  }, [openModelMenuId]);

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

  const beginAction = useCallback((actionId, label) => {
    const startedAt = Date.now();
    const next = {
      id: actionId,
      label: label || actionId,
      startedAt,
    };
    setBusyActionId(actionId);
    setActiveAction(next);
    setActionTimerNow(startedAt);
    setActionResult(null);
    return next;
  }, []);

  const finishAction = useCallback(
    (action, result, error = null) => {
      const completedAt = Date.now();
      const durationMs = Math.max(0, completedAt - action.startedAt);
      const ok = error ? false : result?.ok !== false;
      const message = error ? String(error?.message || error) : result?.message || 'Action completed';
      setActionResult({
        ...(result || {}),
        ok,
        message,
        durationMs,
        startedAt: action.startedAt,
        completedAt,
      });
      void persistExtensionNotification?.({
        kind: ok ? 'event' : 'error',
        source: 'extensions',
        title: `${action.label} ${ok ? 'completed' : 'failed'}`,
        message,
        metadata: {
          extension_id: extensionId,
          action_id: action.id,
          started_at: new Date(action.startedAt).toISOString(),
          completed_at: new Date(completedAt).toISOString(),
          duration_ms: durationMs,
        },
        aggregation_key: `extension-action:${extensionId}:${action.id}:${completedAt}`,
      });
    },
    [extensionId, persistExtensionNotification],
  );

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
      const action = beginAction(actionId, actionLabel(component, actionId));
      try {
        const result = await runExtensionTabAction(
          extensionId,
          actionId,
          actionPayload,
          { timeoutMs: serviceActionTimeoutMs(actionId) },
        );
        finishAction(action, result);
        if (typeof result?.backend_url === 'string') {
          setFieldState((prev) => ({ ...prev, backend_url: result.backend_url }));
        }
        if (isRuntimeModelDetailsForModal(result.details)) {
          setActionDetails(normalizeModelDetailsForModal(result.details, actionPayload.selected_model));
        }
        await load(true);
      } catch (e) {
        finishAction(action, null, e);
      } finally {
        setBusyActionId('');
        setActiveAction(null);
      }
    },
    [beginAction, extensionId, fieldState, finishAction, load],
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
      const actionRun = beginAction(actionId, actionLabel(action, actionId));
      try {
        const result = await runExtensionTabAction(
          extensionId,
          actionId,
          body,
          { timeoutMs: serviceActionTimeoutMs(actionId) },
        );
        finishAction(actionRun, result);
        if (typeof result?.backend_url === 'string') {
          setFieldState((prev) => ({ ...prev, backend_url: result.backend_url }));
        }
        if (actionId === 'refresh') {
          setRefreshKey((prev) => prev + 1);
        }
        const externalUrl = result?.open_external_url || (actionId === 'open_external' ? payload?.content?.open_external_url : '');
        if (externalUrl) window.open(externalUrl, '_blank', 'noopener,noreferrer');
        await load(true);
      } catch (e) {
        finishAction(actionRun, null, e);
      } finally {
        setBusyActionId('');
        setActiveAction(null);
      }
    },
    [beginAction, extensionId, fieldState, finishAction, load, payload?.content?.open_external_url],
  );

  const runAutosave = useCallback(
    async (actionId, key) => {
      const resolvedActionId = String(actionId || '').trim();
      const resolvedKey = String(key || '').trim();
      if (!resolvedActionId || !resolvedKey) return;

      const value = fieldState[resolvedKey] ?? '';
      try {
        const result = await runExtensionTabAction(extensionId, resolvedActionId, { [resolvedKey]: value });
        if (typeof result?.backend_url === 'string') {
          setFieldState((prev) => ({ ...prev, backend_url: result.backend_url }));
        }
        await load(true);
      } catch (e) {
        setActionResult({ ok: false, message: String(e?.message || e) });
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
      setOpenModelMenuPos(null);
      try {
        const result = await runExtensionTabAction(extensionId, actionId, body);
        setActionResult(result);
        if (actionId === 'show_model' && isRuntimeModelDetailsForModal(result.details)) {
          setActionDetails(normalizeModelDetailsForModal(result.details, modelId));
        } else if (isRuntimeModelDetailsForModal(result.details)) {
          setActionDetails(result.details);
        }
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
    if (component?.type === 'steps') {
      const steps = Array.isArray(component.steps) ? component.steps : [];
      return (
        <div key={key} className="extensions-runtime-steps">
          {component.label ? <div className="extensions-runtime-label">{component.label}</div> : null}
          <ol className="extensions-runtime-steps-list">
            {steps.map((step, i) => {
              const done = step.status === 'done';
              return (
                <li
                  key={step.id || i}
                  className={`extensions-runtime-step extensions-runtime-step--${done ? 'done' : 'todo'}`}
                >
                  <span className="material-symbols-outlined extensions-runtime-step-icon" aria-hidden="true">
                    {done ? 'check_circle' : 'radio_button_unchecked'}
                  </span>
                  <div className="extensions-runtime-step-body">
                    <span className="extensions-runtime-step-label">{step.label}</span>
                    {step.command ? (
                      <code className="extensions-runtime-step-code">{step.command}</code>
                    ) : null}
                    {step.hint ? (
                      <span className="extensions-runtime-step-hint">{step.hint}</span>
                    ) : null}
                  </div>
                </li>
              );
            })}
          </ol>
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
            onBlur={() => {
              const autosaveActionId = String(component?.autosave_action_id || '').trim();
              if (!autosaveActionId) return;
              void runAutosave(autosaveActionId, key);
            }}
          />
        </label>
      );
    }
    if (component?.type === 'select') {
      if (key === 'selected_model') return null;
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
      if (['show_model', 'hide_model', 'unhide_model', 'delete_model'].includes(actionId)) return null;
      return (
        <div
          key={key}
          className="extensions-runtime-item extensions-runtime-item--action"
        >
          <div className="extensions-runtime-action-row">
            <CoreUIButton
              variant={component.variant === 'danger' ? 'secondary' : 'primary'}
              onClick={() => void handleAction(component)}
              disabled={Boolean(component.disabled) || busyActionId === actionId}
            >
              {busyActionId === actionId ? 'Working...' : component.label || actionId}
            </CoreUIButton>
            {busyActionId === actionId ? (
              <ActionElapsedChip action={activeAction} nowMs={actionTimerNow} />
            ) : null}
          </div>
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
          const hiddenRaw = String(row?.hidden ?? '').trim().toLowerCase();
          const isHidden = hiddenRaw === 'yes' || hiddenRaw === 'true' || hiddenRaw === '1';
          const menuOpen = openModelMenuId === modelId;

          const modelInfo = row?.model_info;
          const contextLengthKey = modelInfo && typeof modelInfo === 'object'
            ? Object.keys(modelInfo).find((k) => k.endsWith('context_length'))
            : null;
          const contextLength = contextLengthKey ? modelInfo[contextLengthKey] : null;

          const capabilities = Array.isArray(row?.capabilities) ? row.capabilities : [];

          const showTpl = modelActionTemplates.show;
          const hideTpl = modelActionTemplates.hide;
          const unhideTpl = modelActionTemplates.unhide;
          const delTpl = modelActionTemplates.delete;

          const busyShow = busyModelActionKey === `show_model:${modelId}`;
          const busyHide = busyModelActionKey === `hide_model:${modelId}`;
          const busyUnhide = busyModelActionKey === `unhide_model:${modelId}`;
          const busyDel = busyModelActionKey === `delete_model:${modelId}`;

          return (
            <Card
              key={`${key}-model-${modelId || index}`}
              className="extensions-runtime-model-card"
              interactive={Boolean(modelId && showTpl)}
              elevateOnHover={Boolean(modelId && showTpl)}
              onClick={() => {
                if (modelId && showTpl) {
                  setActionDetails(normalizeModelDetailsForModal(row, modelId));
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
                <div className="extensions-runtime-model-card__menu">
                  <button
                    type="button"
                    className="extensions-runtime-model-menu-btn"
                    aria-haspopup="menu"
                    aria-expanded={menuOpen ? 'true' : 'false'}
                    aria-label="Model actions"
                    onClick={(e) => {
                      e.stopPropagation();
                      const rect = e.currentTarget.getBoundingClientRect();
                      const menuWidth = 200;
                      const margin = 12;
                      const left = Math.min(
                        window.innerWidth - menuWidth - margin,
                        Math.max(margin, rect.right - menuWidth),
                      );
                      const top = Math.min(
                        window.innerHeight - margin,
                        rect.bottom + 6,
                      );
                      setOpenModelMenuId((cur) => {
                        const nextOpen = cur !== modelId;
                        setOpenModelMenuPos(nextOpen ? { left, top } : null);
                        return nextOpen ? modelId : '';
                      });
                    }}
                    disabled={!modelId}
                  >
                    <span className="material-symbols-outlined" aria-hidden="true">
                      more_vert
                    </span>
                  </button>
                  {menuOpen ? (
                    <div
                      className="extensions-runtime-model-menu"
                      role="menu"
                      style={openModelMenuPos ? { left: openModelMenuPos.left, top: openModelMenuPos.top } : undefined}
                    >
                      <button
                        type="button"
                        className="extensions-runtime-model-menu-item"
                        role="menuitem"
                        disabled={!modelId || busyShow || Boolean(busyActionId)}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (showTpl) {
                            setActionDetails(normalizeModelDetailsForModal(row, modelId));
                            void runModelMenuAction(showTpl, modelId);
                          } else {
                            setOpenModelMenuId('');
                          }
                        }}
                      >
                        {busyShow ? 'Working...' : 'Show details'}
                      </button>
                      {hideTpl ? (
                        <button
                          type="button"
                          className="extensions-runtime-model-menu-item"
                          role="menuitem"
                          disabled={!modelId || isHidden || busyHide || Boolean(busyActionId)}
                          onClick={(e) => { e.stopPropagation(); void runModelMenuAction(hideTpl, modelId); }}
                        >
                          {busyHide ? 'Working...' : 'Hide model'}
                        </button>
                      ) : null}
                      {unhideTpl ? (
                        <button
                          type="button"
                          className="extensions-runtime-model-menu-item"
                          role="menuitem"
                          disabled={!modelId || !isHidden || busyUnhide || Boolean(busyActionId)}
                          onClick={(e) => { e.stopPropagation(); void runModelMenuAction(unhideTpl, modelId); }}
                        >
                          {busyUnhide ? 'Working...' : 'Unhide model'}
                        </button>
                      ) : null}
                      {delTpl ? (
                        <button
                          type="button"
                          className="extensions-runtime-model-menu-item extensions-runtime-model-menu-item--danger"
                          role="menuitem"
                          disabled={!modelId || busyDel || Boolean(busyActionId)}
                          onClick={(e) => { e.stopPropagation(); void runModelMenuAction(delTpl, modelId); }}
                        >
                          {busyDel ? 'Working...' : 'Delete model'}
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </div>

              <div className="extensions-runtime-model-card__provider">
                <span className="extensions-runtime-model-meta-k">Provider:</span>
                <span className="extensions-runtime-model-meta-v">
                  {row?.provider_id || row?.provider || payload?.extension_id || extensionId || 'unknown'}
                </span>
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
                    <div className="extensions-runtime-model-grid" data-extensions-runtime-model-menu-root="1">
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
                    <div className="extensions-runtime-model-grid" data-extensions-runtime-model-menu-root="1">
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
      return null;
    }
    if (component?.type === 'docker_card') {
      return (
        <CoreUIDockerCard
          key={key}
          name={component.name || payload?.title || title || extensionId}
          description={component.description}
          icon={component.icon || 'deployed_code'}
          status={component.status}
          httpStatus={component.httpStatus}
          fieldKey={component.fieldKey || 'backend_url'}
          busyActionId={busyActionId}
          activeAction={activeAction}
          actionTimerNow={actionTimerNow}
          service={{
            backendUrl: fieldState[component.fieldKey || 'backend_url'] ?? component.backendUrl ?? '',
            backendUrlLabel: component.backendUrlLabel,
            backendUrlPlaceholder: component.backendUrlPlaceholder,
            status: component.status,
            httpStatus: component.httpStatus,
            actions: (component.actions || []).map((action) => ({
              id: action.id,
              label: action.label,
              variant: action.variant,
              icon: action.icon,
              confirm: action.confirm,
              disabled: action.disabled,
              onAction: () => void handleContentAction(action),
            })),
            meta: component.meta || [],
            onBackendUrlChange: (value) => {
              const fk = component.fieldKey || 'backend_url';
              setFieldState((prev) => ({ ...prev, [fk]: value }));
            },
            onBackendUrlBlur: (_value, key) => {
              const fk = key || component.fieldKey || 'backend_url';
              const autosaveActionId = component.autosaveActionId;
              if (!autosaveActionId) return undefined;
              return runAutosave(autosaveActionId, fk);
            },
          }}
        />
      );
    }
    return null;
  };

  if (loading) {
    return <div className="loading">Loading {title || extensionId}...</div>;
  }

  if (runtimeLoadingMessage) {
    return (
      <div className="settings-tab settings-tab--fullwidth tab-view">
        <section className="app-default-card llm-proxy-section-gap">
          <div className="dashboard-card-muted" role="status">
            {runtimeLoadingMessage}
          </div>
        </section>
      </div>
    );
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
  const isServicePanelContent = content?.type === 'service_panel';
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
          {actionResult.durationMs != null ? (
            <span className="extensions-runtime-action-result-duration">
              Duration {formatElapsedMs(actionResult.durationMs)}
            </span>
          ) : null}
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
                  <span key={actionId || action.label} className="extensions-runtime-action-with-timer">
                    <CoreUIButton
                      variant={action.variant === 'danger' ? 'danger' : action.variant === 'primary' ? 'primary' : 'default'}
                      onClick={() => void handleContentAction(action)}
                      disabled={Boolean(action.disabled) || busyActionId === actionId}
                    >
                      {busyActionId === actionId ? 'Working...' : action.label || actionId}
                    </CoreUIButton>
                    {busyActionId === actionId ? (
                      <ActionElapsedChip action={activeAction} nowMs={actionTimerNow} />
                    ) : null}
                  </span>
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
                      onBlur={() => {
                        const autosaveActionId = String(field?.autosave_action_id || '').trim();
                        if (!autosaveActionId) return;
                        void runAutosave(autosaveActionId, key);
                      }}
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

      {isServicePanelContent && content?.service ? (
        <section className="llm-proxy-section-gap">
          <CoreUIDockerCard
            name={content.service.name || content.title || payload?.title || title || extensionId}
            description={content.service.subtitle || content.subtitle}
            icon={content.service.icon || 'deployed_code'}
            status={content.service.status}
            httpStatus={content.service.httpStatus}
            fieldKey={content.service.fieldKey || 'backend_url'}
            busyActionId={busyActionId}
            activeAction={activeAction}
            actionTimerNow={actionTimerNow}
            service={{
              backendUrl: fieldState[content.service.fieldKey || 'backend_url'] ?? content.service.backendUrl ?? '',
              backendUrlLabel: content.service.backendUrlLabel,
              backendUrlPlaceholder: content.service.backendUrlPlaceholder,
              httpStatus: content.service.httpStatus,
              status: content.service.status,
              actions: (content.service.actions || []).map((action) => ({
                id: action.id,
                label: action.label,
                variant: action.variant,
                icon: action.icon,
                confirm: action.confirm,
                disabled: action.disabled,
                onAction: () => void handleContentAction(action),
              })),
              meta: content.service.meta || [],
              onBackendUrlChange: (value) => {
                const fk = content.service.fieldKey || 'backend_url';
                setFieldState((prev) => ({ ...prev, [fk]: value }));
              },
              onBackendUrlBlur: (_value, key) => {
                const fk = key || content.service.fieldKey || 'backend_url';
                const autosaveActionId = (contentFields.find((f) => String(f.key) === fk)?.autosave_action_id) || 'save_backend';
                if (!autosaveActionId) return undefined;
                return runAutosave(autosaveActionId, fk);
              },
            }}
          />
        </section>
      ) : null}

      {isServicePanelContent && !content?.service ? (
        <section className="app-default-card llm-proxy-section-gap extensions-runtime-service-shell">
          <div className="extensions-runtime-service-header">
            <div className="extensions-runtime-service-title-row">
              <div className="extensions-runtime-service-icon" aria-hidden="true">
                <span className="material-symbols-outlined">deployed_code</span>
              </div>
              <div>
                <h2>{content.title || payload?.title || title || extensionId}</h2>
                {content.subtitle ? <p>{content.subtitle}</p> : null}
              </div>
            </div>
            {contentStatus ? (
              <div className={`extensions-runtime-service-state extensions-runtime-service-state--${contentStatus.running ? 'running' : contentStatus.tone === 'error' ? 'error' : 'stopped'}`}>
                <span className="extensions-runtime-service-state__dot" aria-hidden="true" />
                <span>{contentStatus.message || (contentStatus.running ? 'running' : 'stopped')}</span>
                {contentStatus.http_status != null ? <strong>HTTP {contentStatus.http_status}</strong> : null}
              </div>
            ) : null}
          </div>

          <div className="extensions-runtime-service-grid">
            <div className="extensions-runtime-service-main">
              {contentFields.map((field) => {
                const key = String(field.key || '');
                return (
                  <label key={key} className="extensions-runtime-service-field">
                    <span>{field.label || key}</span>
                    <input
                      type={field.secret ? 'password' : 'text'}
                      value={fieldState[key] ?? ''}
                      placeholder={field.placeholder || ''}
                      onChange={(e) => setFieldState((prev) => ({ ...prev, [key]: e.target.value }))}
                      onBlur={() => {
                        const autosaveActionId = String(field?.autosave_action_id || '').trim();
                        if (!autosaveActionId) return;
                        void runAutosave(autosaveActionId, key);
                      }}
                    />
                  </label>
                );
              })}

              <div className="extensions-runtime-service-actions">
                {contentActions.map((action) => {
                  const actionId = String(action?.id || action?.action_id || '');
                  const icon = serviceActionIcon(actionId);
                  return (
                    <span key={actionId || action.label} className="extensions-runtime-action-with-timer">
                      <CoreUIButton
                        variant={action.variant === 'danger' ? 'danger' : action.variant === 'primary' ? 'primary' : 'default'}
                        onClick={() => void handleContentAction(action)}
                        disabled={Boolean(action.disabled) || busyActionId === actionId}
                      >
                        {icon ? <span className="material-symbols-outlined" aria-hidden="true">{icon}</span> : null}
                        {busyActionId === actionId ? 'Working...' : action.label || actionId}
                      </CoreUIButton>
                      {busyActionId === actionId ? (
                        <ActionElapsedChip action={activeAction} nowMs={actionTimerNow} />
                      ) : null}
                    </span>
                  );
                })}
              </div>
            </div>

            <div className="extensions-runtime-service-details">
              {contentDetails.map((item) => (
                <Card key={`${item.label}:${item.value}`} className="extensions-runtime-service-detail">
                  <span>{item.label}</span>
                  <strong>{item.value || '-'}</strong>
                </Card>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {!isServicePanelContent && pages.map((page) => (
        <div key={page.id || 'page'}>
          {(Array.isArray(page.sections) ? page.sections : []).map((section) => {
            const renderedComponents = (Array.isArray(section.components) ? section.components : [])
              .map(renderComponent)
              .filter(Boolean);

            if (renderedComponents.length === 0) return null;

            return (
              <section key={section.id || section.title} className="app-default-card llm-proxy-section-gap">
                <div className="dashboard-card-header">
                  <h2>{section.title || 'Section'}</h2>
                </div>
                <div className="extensions-runtime-section">
                  {renderedComponents}
                </div>
              </section>
            );
          })}
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
