import CoreUIButton from '../CoreUIButton';
import CoreUIModal from '../CoreUIModal';
import CoreUIDockerCard from '../CoreUIDockerCard';
import Card from '../Card';
import ExtensionRuntimeLoadingView, { buildExtensionRuntimeLoadingSteps } from '../ExtensionRuntimeLoadingView';
import { useOptionalNotificationCenter } from '../NotificationCenterContext';
import { useConfirmDialog } from '../useConfirmDialog';
import { formatElapsedMs } from '../../utils/elapsedTime';
import { ActionElapsedChip, ExtensionActionLiveNotification } from './extensionRuntimeActionUi';
import { ExtensionRuntimeModelDetailsContent } from './ExtensionRuntimeModelDetailsContent';
import { renderSchemaComponent } from './ExtensionRuntimeSchemaRenderer';
import {
  collectSchemaComponents,
  formatIsoShort,
  isRuntimeModelDetailsForModal,
  modelIsHidden,
  normalizeModelDetailsForModal,
  serviceActionIcon,
} from './extensionRuntimeTabUtils';
import { useExtensionRuntimeActions } from './useExtensionRuntimeActions';
import { useExtensionRuntimeTab } from './useExtensionRuntimeTab';
import type { ActiveAction } from './reportActionOutcome';
import '../../styles/components/ExtensionRuntimeTab.css';
import { useEffect, useMemo, useState } from 'react';

type ExtensionRuntimeTabProps = {
  extensionId: string;
  title?: string;
  onErrorStateChange?: (state: boolean | 'loading') => void;
};

export default function ExtensionRuntimeTab({
  extensionId,
  title,
  onErrorStateChange,
}: ExtensionRuntimeTabProps) {
  const { confirm, ConfirmDialogHost } = useConfirmDialog();
  const notificationCenter = useOptionalNotificationCenter() as unknown as {
    setLiveActivity?: (...args: unknown[]) => void;
    clearLiveActivity?: (...args: unknown[]) => void;
    persistNotification?: (...args: unknown[]) => void;
  } | null;
  const tab = useExtensionRuntimeTab(extensionId, onErrorStateChange);

  const [busyActionId, setBusyActionId] = useState('');
  const [busyModelActionKey, setBusyModelActionKey] = useState('');
  const [actionResult, setActionResult] = useState<Record<string, unknown> | null>(null);
  const [actionDetails, setActionDetails] = useState<Record<string, unknown> | null>(null);
  const [activeAction, setActiveAction] = useState<ActiveAction | null>(null);
  const [actionTimerNow, setActionTimerNow] = useState(Date.now());
  const [openModelMenuId, setOpenModelMenuId] = useState('');
  const [openModelMenuPos, setOpenModelMenuPos] = useState<{ left: number; top: number } | null>(null);

  const {
    handleAction,
    handleContentAction,
    runAutosave,
    runModelMenuAction,
    runDeleteModel,
  } = useExtensionRuntimeActions({
    extensionId,
    fieldState: tab.fieldState,
    setFieldState: tab.setFieldState,
    setActionResult,
    setActionDetails,
    setRefreshKey: tab.setRefreshKey,
    setBusyActionId,
    setBusyModelActionKey,
    setActiveAction,
    setOpenModelMenuId,
    setOpenModelMenuPos,
    setActionTimerNow,
    load: tab.load,
    confirm,
    persistExtensionNotification: notificationCenter?.persistNotification,
    contentOpenExternalUrl: String((tab.payload?.content as { open_external_url?: string })?.open_external_url || ''),
    isRuntimeModelDetailsForModal,
    normalizeModelDetailsForModal,
  });

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
    const clear = notificationCenter?.clearLiveActivity;
    if (!clear || !activeActionLiveId) return undefined;
    return () => clear(activeActionLiveId);
  }, [activeActionLiveId, notificationCenter?.clearLiveActivity]);

  useEffect(() => {
    const setLive = notificationCenter?.setLiveActivity;
    if (!setLive || !activeAction || !activeActionLiveId) return;
    setLive(
      activeActionLiveId,
      'extensions',
      <ExtensionActionLiveNotification action={activeAction} nowMs={actionTimerNow} />,
      { headerLeading: <span className="notification-center-card-spinner" aria-hidden="true" /> },
    );
  }, [activeAction, activeActionLiveId, actionTimerNow, notificationCenter?.setLiveActivity]);

  useEffect(() => {
    if (!openModelMenuId) return undefined;
    const onDown = (e: MouseEvent) => {
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
    () => (Array.isArray((tab.payload?.schema as { pages?: unknown[] })?.pages)
      ? (tab.payload?.schema as { pages: unknown[] }).pages
      : []),
    [tab.payload],
  );

  const modelActionTemplates = useMemo(() => {
    const comps = collectSchemaComponents(tab.payload?.schema);
    const pick = (id: string) => comps.find(
      (c) => String(c?.type || '').toLowerCase() === 'action' && String(c?.action_id || '') === id,
    );
    return {
      show: pick('show_model'),
      hide: pick('hide_model'),
      unhide: pick('unhide_model'),
      delete: pick('delete_model'),
    };
  }, [tab.payload?.schema]);

  const schemaCtx = useMemo(() => ({
    extensionId,
    title,
    payload: tab.payload,
    fieldState: tab.fieldState,
    setFieldState: tab.setFieldState,
    busyActionId,
    busyModelActionKey,
    activeAction,
    actionTimerNow,
    openModelMenuId,
    openModelMenuPos,
    setOpenModelMenuId,
    setOpenModelMenuPos,
    modelActionTemplates,
    handleAction,
    handleContentAction,
    runAutosave,
    runModelMenuAction,
    setActionDetails,
    normalizeModelDetailsForModal,
  }), [
    extensionId,
    title,
    tab.payload,
    tab.fieldState,
    tab.setFieldState,
    busyActionId,
    busyModelActionKey,
    activeAction,
    actionTimerNow,
    openModelMenuId,
    openModelMenuPos,
    modelActionTemplates,
    handleAction,
    handleContentAction,
    runAutosave,
    runModelMenuAction,
  ]);

  if (tab.loading) {
    return (
      <ExtensionRuntimeLoadingView
        title={title || ''}
        extensionId={extensionId}
        elapsedMs={Math.max(0, tab.loadTimerNow - tab.loadStartedAt)}
        steps={buildExtensionRuntimeLoadingSteps({
          endpoint: `/api/webui/extensions/${extensionId}/tab`,
          loadState: tab.loadState,
          mode: 'request',
        } as Record<string, unknown>) as never}
      />
    );
  }

  if (tab.runtimeLoadingMessage || (tab.waitingForTabPayload && !tab.hasRenderablePayload)) {
    return (
      <ExtensionRuntimeLoadingView
        title={title || ''}
        extensionId={extensionId}
        elapsedMs={Math.max(0, tab.loadTimerNow - tab.loadStartedAt)}
        message={tab.runtimeLoadingMessage || String(tab.loadState?.error || 'Extension tab payload is loading.')}
        steps={buildExtensionRuntimeLoadingSteps({
          endpoint: `/api/webui/extensions/${extensionId}/tab`,
          loadState: tab.loadState,
          message: tab.runtimeLoadingMessage || String(tab.loadState?.error || ''),
          mode: tab.runtimeLoadingMessage ? 'runtime' : 'payload',
        } as Record<string, unknown>) as never}
      />
    );
  }

  if (tab.error) {
    return (
      <div className="settings-tab settings-tab--fullwidth tab-view">
        <section className="app-default-card llm-proxy-section-gap">
          <div className="dashboard-card-error" role="alert">{tab.error}</div>
        </section>
      </div>
    );
  }

  const content = (tab.payload?.content || null) as Record<string, unknown> | null;
  const isIframeContent = content?.type === 'iframe';
  const isServicePanelContent = content?.type === 'service_panel';
  const contentFields = Array.isArray(content?.fields) ? content.fields as Record<string, unknown>[] : [];
  const contentActions = Array.isArray(content?.actions) ? content.actions as Record<string, unknown>[] : [];
  const contentDetails = Array.isArray(content?.details) ? content.details as Record<string, unknown>[] : [];
  const contentStatus = tab.payload?.status && typeof tab.payload.status === 'object'
    ? tab.payload.status as Record<string, unknown>
    : null;

  const renderContentAction = (action: Record<string, unknown>) => {
    const actionId = String(action?.id || action?.action_id || '');
    const icon = serviceActionIcon(actionId);
    return (
      <span key={actionId || String(action.label)} className="extensions-runtime-action-with-timer">
        <CoreUIButton
          variant={action.variant === 'danger' ? 'danger' : action.variant === 'primary' ? 'primary' : 'default'}
          onClick={() => void handleContentAction(action)}
          disabled={Boolean(action.disabled) || busyActionId === actionId}
        >
          {icon ? <span className="material-symbols-outlined" aria-hidden="true">{icon}</span> : null}
          {busyActionId === actionId ? 'Working...' : String(action.label || actionId)}
        </CoreUIButton>
        {busyActionId === actionId ? (
          <ActionElapsedChip action={activeAction} nowMs={actionTimerNow} />
        ) : null}
      </span>
    );
  };

  return (
    <div className="settings-tab settings-tab--fullwidth tab-view">
      {tab.waitingForTabPayload && tab.hasRenderablePayload ? (
        <div className="dashboard-card-muted llm-proxy-section-gap-sm extensions-runtime-refreshing-banner" role="status">
          <span className="notification-center-card-spinner" aria-hidden="true" />
          Refreshing extension payload
          {tab.loadState?.cached_at ? (
            <span className="extensions-runtime-refreshing-banner__time">
              Last cached {formatIsoShort(tab.loadState.cached_at)}
            </span>
          ) : null}
        </div>
      ) : null}

      {actionResult ? (
        <div
          className={actionResult.ok === false ? 'dashboard-card-error llm-proxy-section-gap-sm' : 'dashboard-card-muted llm-proxy-section-gap-sm'}
          role={actionResult.ok === false ? 'alert' : 'status'}
        >
          {String(actionResult.message || 'Action completed')}
          {actionResult.durationMs != null ? (
            <span className="extensions-runtime-action-result-duration">
              Duration {formatElapsedMs(Number(actionResult.durationMs))}
            </span>
          ) : null}
        </div>
      ) : null}

      {isIframeContent ? (
        <section className="app-default-card llm-proxy-section-gap extensions-runtime-frame-shell">
          <div className="dashboard-card-header extensions-runtime-frame-header">
            <div>
              <h2>{String(content?.title || tab.payload?.title || title || extensionId)}</h2>
              {contentStatus ? (
                <div className="extensions-runtime-frame-status">
                  <span
                    className={`extensions-runtime-frame-status__dot ${contentStatus.running ? 'running' : contentStatus.tone === 'error' ? 'error' : 'stopped'}`}
                    aria-hidden="true"
                  />
                  <span>{String(contentStatus.message || (contentStatus.running ? 'running' : 'stopped'))}</span>
                  {contentStatus.http_status != null ? <span>HTTP {String(contentStatus.http_status)}</span> : null}
                </div>
              ) : null}
            </div>
            <div className="dashboard-card-actions extensions-runtime-frame-actions">
              {contentActions.map(renderContentAction)}
            </div>
          </div>
          {contentFields.length ? (
            <div className="extensions-runtime-frame-fields">
              {contentFields.map((field) => {
                const key = String(field.key || '');
                return (
                  <label key={key} className="extensions-runtime-frame-field">
                    <span>{String(field.label || key)}</span>
                    <input
                      type={field.secret ? 'password' : 'text'}
                      value={tab.fieldState[key] ?? ''}
                      placeholder={String(field.placeholder || '')}
                      onChange={(e) => tab.setFieldState((prev) => ({ ...prev, [key]: e.target.value }))}
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
                  <span>{String(item.label)}</span>
                  <strong>{String(item.value || '-')}</strong>
                </div>
              ))}
            </div>
          ) : null}
          <div className="extensions-runtime-frame-wrap">
            <iframe
              key={tab.refreshKey}
              className="extensions-runtime-frame"
              title={String(content?.title || tab.payload?.title || title || extensionId)}
              src={String(content?.src || 'about:blank')}
              allow="clipboard-read; clipboard-write"
            />
          </div>
        </section>
      ) : null}

      {isServicePanelContent && content?.service ? (
        <section className="llm-proxy-section-gap">
          <CoreUIDockerCard
            name={String((content.service as Record<string, unknown>).name || content.title || tab.payload?.title || title || extensionId)}
            description={(content.service as Record<string, unknown>).subtitle as string || content.subtitle as string}
            icon={String((content.service as Record<string, unknown>).icon || 'deployed_code')}
            iconUrl={String((content.service as Record<string, unknown>).iconUrl || tab.payload?.icon_url || '')}
            status={(content.service as Record<string, unknown>).status as { tone?: string; label: string }}
            httpStatus={(content.service as Record<string, unknown>).httpStatus as string}
            fieldKey={String((content.service as Record<string, unknown>).fieldKey || 'backend_url')}
            busyActionId={busyActionId}
            activeAction={activeAction ?? undefined}
            actionTimerNow={actionTimerNow}
            service={{
              iconUrl: String((content.service as Record<string, unknown>).iconUrl || tab.payload?.icon_url || ''),
              backendUrl: tab.fieldState[String((content.service as Record<string, unknown>).fieldKey || 'backend_url')]
                ?? String((content.service as Record<string, unknown>).backendUrl ?? ''),
              backendUrlLabel: (content.service as Record<string, unknown>).backendUrlLabel,
              backendUrlPlaceholder: (content.service as Record<string, unknown>).backendUrlPlaceholder,
              httpStatus: (content.service as Record<string, unknown>).httpStatus,
              status: (content.service as Record<string, unknown>).status,
              actions: ((content.service as Record<string, unknown>).actions as Record<string, unknown>[] || []).map((action) => ({
                id: action.id,
                label: action.label,
                variant: action.variant,
                icon: action.icon,
                disabled: action.disabled,
                confirm: action.confirm,
                payload_keys: action.payload_keys,
                onAction: () => void handleContentAction(action),
              })),
              meta: (content.service as Record<string, unknown>).meta || [],
              onBackendUrlChange: (value: string) => {
                const fk = String((content.service as Record<string, unknown>).fieldKey || 'backend_url');
                tab.setFieldState((prev) => ({ ...prev, [fk]: value }));
              },
              onBackendUrlBlur: (_value: string, key?: string) => {
                const fk = key || String((content.service as Record<string, unknown>).fieldKey || 'backend_url');
                const autosaveActionId = String(
                  contentFields.find((f) => String(f.key) === fk)?.autosave_action_id || 'save_backend',
                );
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
                {tab.payload?.icon_url ? (
                  /\.svg(\?|$)/i.test(String(tab.payload.icon_url)) ? (
                    <span
                      className="extensions-runtime-service-icon-image extensions-runtime-service-icon-image--masked"
                      style={{
                        maskImage: `url(${tab.payload.icon_url})`,
                        WebkitMaskImage: `url(${tab.payload.icon_url})`,
                      }}
                    />
                  ) : (
                    <img className="extensions-runtime-service-icon-image" src={String(tab.payload.icon_url)} alt="" aria-hidden="true" />
                  )
                ) : (
                  <span className="material-symbols-outlined">deployed_code</span>
                )}
              </div>
              <div>
                <h2>{String(content?.title || tab.payload?.title || title || extensionId)}</h2>
                {content?.subtitle ? <p>{String(content.subtitle)}</p> : null}
              </div>
            </div>
            {contentStatus ? (
              <div className={`extensions-runtime-service-state extensions-runtime-service-state--${contentStatus.running ? 'running' : contentStatus.tone === 'error' ? 'error' : 'stopped'}`}>
                <span className="extensions-runtime-service-state__dot" aria-hidden="true" />
                <span>{String(contentStatus.message || (contentStatus.running ? 'running' : 'stopped'))}</span>
                {contentStatus.http_status != null ? <strong>HTTP {String(contentStatus.http_status)}</strong> : null}
              </div>
            ) : null}
          </div>
          <div className="extensions-runtime-service-grid">
            <div className="extensions-runtime-service-main">
              {contentFields.map((field) => {
                const key = String(field.key || '');
                return (
                  <label key={key} className="extensions-runtime-service-field">
                    <span>{String(field.label || key)}</span>
                    <input
                      type={field.secret ? 'password' : 'text'}
                      value={tab.fieldState[key] ?? ''}
                      placeholder={String(field.placeholder || '')}
                      onChange={(e) => tab.setFieldState((prev) => ({ ...prev, [key]: e.target.value }))}
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
                {contentActions.map(renderContentAction)}
              </div>
            </div>
            <div className="extensions-runtime-service-details">
              {contentDetails.map((item) => (
                <Card key={`${item.label}:${item.value}`} className="extensions-runtime-service-detail">
                  <span>{String(item.label)}</span>
                  <strong>{String(item.value || '-')}</strong>
                </Card>
              ))}
            </div>
          </div>
        </section>
      ) : null}

      {!isServicePanelContent && pages.map((page) => {
        const p = page as Record<string, unknown>;
        return (
          <div key={String(p.id || 'page')}>
            {(Array.isArray(p.sections) ? p.sections as Record<string, unknown>[] : []).map((section) => {
              const sectionId = String(section.id || section.title || 'section');
              const renderedComponents = (Array.isArray(section.components) ? section.components as Record<string, unknown>[] : [])
                .map((component, index) => renderSchemaComponent(component, sectionId, index, schemaCtx))
                .filter(Boolean);
              if (renderedComponents.length === 0) return null;
              return (
                <section key={String(section.id || section.title)} className="app-default-card llm-proxy-section-gap">
                  <div className="dashboard-card-header">
                    <h2>{String(section.title || 'Section')}</h2>
                  </div>
                  <div className="extensions-runtime-section">{renderedComponents}</div>
                </section>
              );
            })}
          </div>
        );
      })}

      {actionDetails ? (() => {
        const modelId = String(actionDetails?.id ?? actionDetails?.model ?? '').trim();
        const isHidden = modelIsHidden(actionDetails);
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
            footer={(
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
                    onClick={() => void runDeleteModel(delTpl, modelId, () => setActionDetails(null))}
                    disabled={busyDel || Boolean(busyActionId)}
                  >
                    <span className="material-symbols-outlined" aria-hidden="true">delete</span>
                    {busyDel ? 'Working…' : 'Delete model'}
                  </CoreUIButton>
                ) : null}
              </div>
            )}
          >
            <ExtensionRuntimeModelDetailsContent model={actionDetails} />
          </CoreUIModal>
        );
      })() : null}

      <ConfirmDialogHost />
    </div>
  );
}
