import CoreUIButton from '../CoreUIButton';
import CoreUIDockerCard from '../CoreUIDockerCard';
import ExtensionRuntimeModelCard, { type ModelActionTemplates } from './ExtensionRuntimeModelCard';
import { ActionElapsedChip } from './extensionRuntimeActionUi';
import type { ActiveAction } from './reportActionOutcome';

export type SchemaRendererContext = {
  extensionId: string;
  title?: string;
  payload: Record<string, unknown> | null;
  fieldState: Record<string, string>;
  setFieldState: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  busyActionId: string;
  busyModelActionKey: string;
  activeAction: ActiveAction | null;
  actionTimerNow: number;
  openModelMenuId: string;
  openModelMenuPos: { left: number; top: number } | null;
  setOpenModelMenuId: React.Dispatch<React.SetStateAction<string>>;
  setOpenModelMenuPos: React.Dispatch<React.SetStateAction<{ left: number; top: number } | null>>;
  modelActionTemplates: ModelActionTemplates;
  handleAction: (component: Record<string, unknown>) => void;
  handleContentAction: (action: Record<string, unknown>) => void;
  runAutosave: (actionId: string, key: string) => void;
  runModelMenuAction: (template: Record<string, unknown>, modelId: string) => void;
  setActionDetails: React.Dispatch<React.SetStateAction<Record<string, unknown> | null>>;
  normalizeModelDetailsForModal: (details: unknown, modelId?: string) => Record<string, unknown>;
};

function buildDockerServiceProps(
  component: Record<string, unknown>,
  ctx: SchemaRendererContext,
) {
  const fieldKey = String(component.fieldKey || 'backend_url');
  return {
    iconUrl: String(component.iconUrl || ctx.payload?.icon_url || ''),
    backendUrl: ctx.fieldState[fieldKey] ?? String(component.backendUrl ?? ''),
    backendUrlLabel: component.backendUrlLabel,
    backendUrlPlaceholder: component.backendUrlPlaceholder,
    status: component.status,
    httpStatus: component.httpStatus,
    actions: (Array.isArray(component.actions) ? component.actions : []).map((action) => {
      const a = action as Record<string, unknown>;
      return {
        id: a.id,
        label: a.label,
        variant: a.variant,
        icon: a.icon,
        disabled: a.disabled,
        confirm: a.confirm,
        payload_keys: a.payload_keys,
        onAction: () => void ctx.handleContentAction(a),
      };
    }),
    meta: component.meta || [],
    onBackendUrlChange: (value: string) => {
      ctx.setFieldState((prev) => ({ ...prev, [fieldKey]: value }));
    },
    onBackendUrlBlur: (_value: string, key?: string) => {
      const fk = key || fieldKey;
      const autosaveActionId = component.autosaveActionId;
      if (!autosaveActionId) return undefined;
      return ctx.runAutosave(String(autosaveActionId), fk);
    },
  };
}

export function renderSchemaComponent(
  component: Record<string, unknown>,
  sectionId: string,
  index: number,
  ctx: SchemaRendererContext,
): React.ReactNode {
  const key = String(component?.key ?? component?.action_id ?? `${sectionId}-${index}`);
  const setField = (fieldKey: string, value: string) => {
    ctx.setFieldState((prev) => ({ ...prev, [fieldKey]: value }));
  };

  if (component?.type === 'status') {
    const status = String(component.status || 'unknown');
    return (
      <div key={key} className="extensions-runtime-item">
        <div className="extensions-runtime-label">{String(component.label || 'Status')}</div>
        <div className={`extensions-runtime-status extensions-runtime-status--${status}`}>
          <strong>{status}</strong>
          {component.message ? (
            <>
              {' '}
              <span>{String(component.message)}</span>
            </>
          ) : null}
        </div>
      </div>
    );
  }

  if (component?.type === 'text') {
    return (
      <div key={key} className="extensions-runtime-item">
        <div className="extensions-runtime-label">{String(component.label || key)}</div>
          <div className="extensions-runtime-text">{String(component.value ?? '—')}</div>
      </div>
    );
  }

  if (component?.type === 'steps') {
    const steps = Array.isArray(component.steps) ? component.steps : [];
    return (
      <div key={key} className="extensions-runtime-steps">
        {component.label ? <div className="extensions-runtime-label">{String(component.label)}</div> : null}
        <ol className="extensions-runtime-steps-list">
          {steps.map((step, i) => {
            const s = step as Record<string, unknown>;
            const done = s.status === 'done';
            return (
              <li
                key={String(s.id || i)}
                className={`extensions-runtime-step extensions-runtime-step--${done ? 'done' : 'todo'}`}
              >
                <span className="material-symbols-outlined extensions-runtime-step-icon" aria-hidden="true">
                  {done ? 'check_circle' : 'radio_button_unchecked'}
                </span>
                <div className="extensions-runtime-step-body">
                  <span className="extensions-runtime-step-label">{String(s.label)}</span>
                  {s.command ? <code className="extensions-runtime-step-code">{String(s.command)}</code> : null}
                  {s.hint ? <span className="extensions-runtime-step-hint">{String(s.hint)}</span> : null}
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
        <div className="extensions-runtime-label">{String(component.label || key)}</div>
        <input
          type={component.secret ? 'password' : 'text'}
          value={ctx.fieldState[key] ?? ''}
          placeholder={String(component.placeholder || '')}
          onChange={(e) => setField(key, e.target.value)}
          onBlur={() => {
            const autosaveActionId = String(component?.autosave_action_id || '').trim();
            if (!autosaveActionId) return;
            void ctx.runAutosave(autosaveActionId, key);
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
        <div className="extensions-runtime-label">{String(component.label || key)}</div>
        <select
          value={ctx.fieldState[key] ?? String(component.value ?? '')}
          onChange={(e) => setField(key, e.target.value)}
        >
          {options.map((option) => {
            const o = option as { value?: string; label?: string };
            return (
              <option key={`${key}-${o.value}`} value={o.value}>
                {o.label || o.value}
              </option>
            );
          })}
        </select>
      </label>
    );
  }

  if (component?.type === 'action') {
    const actionId = String(component.action_id || '');
    if (['show_model', 'hide_model', 'unhide_model', 'delete_model'].includes(actionId)) return null;
    return (
      <div key={key} className="extensions-runtime-item extensions-runtime-item--action">
        <div className="extensions-runtime-action-row">
          <CoreUIButton
            variant={component.variant === 'danger' ? 'danger' : 'primary'}
            onClick={() => void ctx.handleAction(component)}
            disabled={Boolean(component.disabled) || ctx.busyActionId === actionId}
          >
            {ctx.busyActionId === actionId ? 'Working...' : String(component.label || actionId)}
          </CoreUIButton>
          {ctx.busyActionId === actionId ? (
            <ActionElapsedChip action={ctx.activeAction} nowMs={ctx.actionTimerNow} />
          ) : null}
        </div>
      </div>
    );
  }

  if (component?.type === 'table') {
    const columns = Array.isArray(component.columns) ? component.columns : [];
    const rows = Array.isArray(component.rows) ? component.rows : [];

    if (key === 'provider_models') {
      const rowRecords = rows as Record<string, unknown>[];
      const cloudModels = rowRecords
        .filter((r) => String(r?.id ?? r?.model ?? '').toLowerCase().endsWith('cloud'))
        .sort((a, b) => String(a?.id ?? a?.model ?? '').localeCompare(String(b?.id ?? b?.model ?? '')));
      const localModels = rowRecords
        .filter((r) => !String(r?.id ?? r?.model ?? '').toLowerCase().endsWith('cloud'))
        .sort((a, b) => String(a?.id ?? a?.model ?? '').localeCompare(String(b?.id ?? b?.model ?? '')));

      const renderGrid = (models: Record<string, unknown>[]) => (
        <div className="extensions-runtime-model-grid" data-extensions-runtime-model-menu-root="1">
          {models.map((row, rowIndex) => {
            const modelId = String(row?.id ?? row?.model ?? '').trim();
            return (
              <ExtensionRuntimeModelCard
                key={`${key}-model-${modelId || rowIndex}`}
                row={row}
                index={rowIndex}
                extensionId={ctx.extensionId}
                payloadExtensionId={String(ctx.payload?.extension_id || '')}
                menuOpen={ctx.openModelMenuId === modelId}
                menuPosition={ctx.openModelMenuPos}
                busyModelActionKey={ctx.busyModelActionKey}
                busyActionId={ctx.busyActionId}
                templates={ctx.modelActionTemplates}
                onOpenMenu={(id, pos) => {
                  ctx.setOpenModelMenuId(pos ? id : '');
                  ctx.setOpenModelMenuPos(pos);
                }}
                onShowDetails={(r, id) => {
                  ctx.setActionDetails(ctx.normalizeModelDetailsForModal(r, id));
                }}
                onModelMenuAction={ctx.runModelMenuAction}
              />
            );
          })}
        </div>
      );

      return (
        <div key={key} className="extensions-runtime-item">
          <div className="extensions-runtime-label">{String(component.label || 'Installed models')}</div>
          {rows.length === 0 ? (
            <div className="extensions-runtime-text">No models.</div>
          ) : (
            <>
              {cloudModels.length > 0 ? (
                <>
                  <div className="extensions-runtime-label--large">
                    <span className="material-symbols-outlined">cloud</span>
                    Cloud
                  </div>
                  {renderGrid(cloudModels)}
                </>
              ) : null}
              {localModels.length > 0 ? (
                <>
                  <div className="extensions-runtime-label--large">
                    <span className="material-symbols-outlined">cloud_off</span>
                    Local
                  </div>
                  {renderGrid(localModels)}
                </>
              ) : null}
            </>
          )}
        </div>
      );
    }

    return (
      <div key={key} className="extensions-runtime-item">
        <div className="extensions-runtime-label">{String(component.label || key)}</div>
        {rows.length === 0 ? (
          <div className="extensions-runtime-text">No rows.</div>
        ) : (
          <div className="extensions-runtime-table-wrap">
            <table className="collections-table">
              <thead>
                <tr>
                  {columns.map((column) => {
                    const c = column as { key?: string; label?: string };
                    return <th key={`${key}-${c.key}`}>{c.label || c.key}</th>;
                  })}
                </tr>
              </thead>
              <tbody>
                {rows.map((row, rowIndex) => {
                  const r = row as Record<string, unknown>;
                  return (
                    <tr key={`${key}-row-${rowIndex}`}>
                      {columns.map((column) => {
                        const c = column as { key?: string };
                        return <td key={`${key}-${rowIndex}-${c.key}`}>{String(r?.[c.key!] ?? '—')}</td>;
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    );
  }

  if (component?.type === 'diagnostics') return null;

  if (component?.type === 'docker_card') {
    const fieldKey = String(component.fieldKey || 'backend_url');
    return (
      <CoreUIDockerCard
        key={key}
        name={String(component.name || ctx.payload?.title || ctx.title || ctx.extensionId)}
        description={component.description as string | undefined}
        icon={String(component.icon || 'deployed_code')}
        iconUrl={String(component.iconUrl || ctx.payload?.icon_url || '')}
        status={component.status as { tone?: string; label: string } | undefined}
        httpStatus={component.httpStatus as string | undefined}
        fieldKey={fieldKey}
        busyActionId={ctx.busyActionId}
        activeAction={ctx.activeAction ?? undefined}
        actionTimerNow={ctx.actionTimerNow}
        service={buildDockerServiceProps(component, ctx)}
      />
    );
  }

  return null;
}
