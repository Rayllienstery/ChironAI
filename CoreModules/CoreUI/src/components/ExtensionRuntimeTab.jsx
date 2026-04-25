import { useCallback, useEffect, useMemo, useState } from 'react';
import Card from './Card';
import CoreUIButton from './CoreUIButton';
import { getExtensionTab, runExtensionTabAction } from '../services/api';

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

function ExtensionRuntimeTab({ extensionId, title, onErrorStateChange }) {
  const [payload, setPayload] = useState(null);
  const [fieldState, setFieldState] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [busyActionId, setBusyActionId] = useState('');
  const [actionResult, setActionResult] = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getExtensionTab(extensionId);
      setPayload(data);
      setFieldState((prev) => ({ ...extractFieldDefaults(data?.schema), ...prev }));
      onErrorStateChange?.(false);
    } catch (e) {
      const msg = String(e?.message || e);
      setError(msg);
      onErrorStateChange?.(true);
    } finally {
      setLoading(false);
    }
  }, [extensionId, onErrorStateChange]);

  useEffect(() => {
    void load();
  }, [load]);

  const pages = useMemo(
    () => (Array.isArray(payload?.schema?.pages) ? payload.schema.pages : []),
    [payload],
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

  const renderComponent = (component) => {
    const key = String(component?.key || component?.action_id || Math.random());
    if (component?.type === 'status') {
      const status = String(component.status || 'unknown');
      return (
        <div key={key} className="extensions-runtime-item">
          <div className="extensions-runtime-label">{component.label || 'Status'}</div>
          <div className={`extensions-runtime-status extensions-runtime-status--${status}`}>
            <strong>{status}</strong>
            {component.message ? <span>{component.message}</span> : null}
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
        <div className="dashboard-card-error" role="alert">
          {error}
        </div>
      </div>
    );
  }

  return (
    <div className="settings-tab settings-tab--fullwidth">
      <div className="dashboard-card-actions llm-proxy-section-gap">
        <CoreUIButton variant="primary" onClick={() => void load()}>
          Refresh
        </CoreUIButton>
      </div>

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
            <Card key={section.id || section.title} className="llm-proxy-section-gap">
              <div className="dashboard-card-header">
                <h3>{section.title || 'Section'}</h3>
              </div>
              <div className="extensions-runtime-section">
                {(Array.isArray(section.components) ? section.components : []).map(renderComponent)}
              </div>
            </Card>
          ))}
        </div>
      ))}
    </div>
  );
}

export default ExtensionRuntimeTab;
