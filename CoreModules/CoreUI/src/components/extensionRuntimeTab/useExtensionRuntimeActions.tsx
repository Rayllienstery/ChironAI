import { useCallback } from 'react';
import { runExtensionTabAction } from '../../services/api';
import type { ConfirmOptions } from '../useConfirmDialog';
import type { FieldState } from './comparePayload';
import {
  actionLabel,
  buildActionPayload,
  serviceActionTimeoutMs,
} from './buildActionPayload';
import {
  buildActionOutcome,
  buildExtensionActionNotification,
  buildSimpleActionOutcome,
  type ActiveAction,
} from './reportActionOutcome';

type ConfirmFn = (options: ConfirmOptions) => Promise<boolean>;

type PersistNotificationFn = (input: ReturnType<typeof buildExtensionActionNotification>) => void;

export type UseExtensionRuntimeActionsOptions = {
  extensionId: string;
  fieldState: FieldState;
  setFieldState: React.Dispatch<React.SetStateAction<FieldState>>;
  setActionResult: React.Dispatch<React.SetStateAction<Record<string, unknown> | null>>;
  setActionDetails: React.Dispatch<React.SetStateAction<Record<string, unknown> | null>>;
  setRefreshKey: React.Dispatch<React.SetStateAction<number>>;
  setBusyActionId: React.Dispatch<React.SetStateAction<string>>;
  setBusyModelActionKey: React.Dispatch<React.SetStateAction<string>>;
  setActiveAction: React.Dispatch<React.SetStateAction<ActiveAction | null>>;
  setOpenModelMenuId: React.Dispatch<React.SetStateAction<string>>;
  setOpenModelMenuPos: React.Dispatch<React.SetStateAction<{ top: number; left: number } | null>>;
  setActionTimerNow: React.Dispatch<React.SetStateAction<number>>;
  load: (silent?: boolean) => Promise<void>;
  confirm: ConfirmFn;
  persistExtensionNotification?: PersistNotificationFn;
  contentOpenExternalUrl?: string;
  isRuntimeModelDetailsForModal: (details: unknown) => boolean;
  normalizeModelDetailsForModal: (details: unknown, modelId?: string) => Record<string, unknown>;
};

export function useExtensionRuntimeActions({
  extensionId,
  fieldState,
  setFieldState,
  setActionResult,
  setActionDetails,
  setRefreshKey,
  setBusyActionId,
  setBusyModelActionKey,
  setActiveAction,
  setOpenModelMenuId,
  setOpenModelMenuPos,
  setActionTimerNow,
  load,
  confirm,
  persistExtensionNotification,
  contentOpenExternalUrl,
  isRuntimeModelDetailsForModal,
  normalizeModelDetailsForModal,
}: UseExtensionRuntimeActionsOptions) {
  const reportOutcome = useCallback(
    (action: ActiveAction, result: Record<string, unknown> | null | undefined, error: unknown = null) => {
      const outcome = buildActionOutcome(action, result, error);
      setActionResult(outcome);
      void persistExtensionNotification?.(buildExtensionActionNotification(action, extensionId, outcome));
      return outcome;
    },
    [extensionId, persistExtensionNotification, setActionResult],
  );

  const reportSimpleError = useCallback(
    (error: unknown) => {
      setActionResult(buildSimpleActionOutcome(error));
    },
    [setActionResult],
  );

  const beginAction = useCallback((actionId: string, label: string): ActiveAction => {
    const startedAt = Date.now();
    const next: ActiveAction = {
      id: actionId,
      label: label || actionId,
      startedAt,
    };
    setBusyActionId(actionId);
    setActiveAction(next);
    setActionTimerNow(startedAt);
    setActionResult(null);
    return next;
  }, [setActionResult, setActionTimerNow, setActiveAction, setBusyActionId]);

  const applyBackendUrl = useCallback((result: Record<string, unknown> | null | undefined) => {
    if (typeof result?.backend_url === 'string') {
      setFieldState((prev) => ({ ...prev, backend_url: result.backend_url as string }));
    }
  }, [setFieldState]);

  const runTabAction = useCallback(async ({
    actionId,
    labelSource,
    confirmMessage,
    payloadKeys,
    payloadOverrides = {},
    trackPrimaryBusy = true,
    notify = true,
    silentLoad = true,
    onSuccess,
  }: {
    actionId: string;
    labelSource?: { label?: string; title?: string } | null;
    confirmMessage?: unknown;
    payloadKeys?: unknown;
    payloadOverrides?: Record<string, string>;
    trackPrimaryBusy?: boolean;
    notify?: boolean;
    silentLoad?: boolean;
    onSuccess?: (result: Record<string, unknown>) => void | Promise<void>;
  }) => {
    const resolvedActionId = String(actionId || '').trim();
    if (!resolvedActionId) return null;

    if (!(await confirm({ message: String(confirmMessage ?? ''), variant: 'danger' }))) return null;

    const body = buildActionPayload(payloadKeys, fieldState, payloadOverrides);
    const action = trackPrimaryBusy
      ? beginAction(resolvedActionId, actionLabel(labelSource, resolvedActionId))
      : null;

    try {
      const result = await runExtensionTabAction(
        extensionId,
        resolvedActionId,
        body,
        { timeoutMs: serviceActionTimeoutMs(resolvedActionId) },
      ) as Record<string, unknown>;

      if (notify && action) {
        reportOutcome(action, result);
      } else {
        setActionResult(result);
      }

      applyBackendUrl(result);
      await onSuccess?.(result);
      await load(silentLoad);
      return result;
    } catch (error) {
      if (notify && action) {
        reportOutcome(action, null, error);
      } else {
        reportSimpleError(error);
      }
      return null;
    } finally {
      if (trackPrimaryBusy) {
        setBusyActionId('');
        setActiveAction(null);
      }
    }
  }, [
    applyBackendUrl,
    beginAction,
    confirm,
    extensionId,
    fieldState,
    load,
    reportOutcome,
    reportSimpleError,
    setActionResult,
    setActiveAction,
    setBusyActionId,
  ]);

  const handleAction = useCallback(async (component: Record<string, unknown>) => {
    const actionId = String(component?.action_id || '').trim();
    if (!actionId) return;

    await runTabAction({
      actionId,
      labelSource: component,
      confirmMessage: component?.confirm,
      payloadKeys: component?.payload_keys,
      onSuccess: (result) => {
        if (isRuntimeModelDetailsForModal(result.details)) {
          const payload = buildActionPayload(component?.payload_keys, fieldState);
          setActionDetails(
            normalizeModelDetailsForModal(result.details, payload.selected_model),
          );
        }
      },
    });
  }, [
    fieldState,
    isRuntimeModelDetailsForModal,
    normalizeModelDetailsForModal,
    runTabAction,
    setActionDetails,
  ]);

  const handleContentAction = useCallback(async (action: Record<string, unknown>) => {
    const actionId = String(action?.id || action?.action_id || '').trim();
    if (!actionId) return;

    await runTabAction({
      actionId,
      labelSource: action,
      confirmMessage: action?.confirm,
      payloadKeys: action?.payload_keys,
      onSuccess: (result) => {
        if (actionId === 'refresh') {
          setRefreshKey((prev) => prev + 1);
        }
        const externalUrl = result?.open_external_url
          || (actionId === 'open_external' ? contentOpenExternalUrl : '');
        if (externalUrl) {
          window.open(String(externalUrl), '_blank', 'noopener,noreferrer');
        }
      },
    });
  }, [contentOpenExternalUrl, runTabAction, setRefreshKey]);

  const runAutosave = useCallback(async (actionId: string, key: string) => {
    const resolvedActionId = String(actionId || '').trim();
    const resolvedKey = String(key || '').trim();
    if (!resolvedActionId || !resolvedKey) return;

    const value = fieldState[resolvedKey] ?? '';
    try {
      const result = await runExtensionTabAction(extensionId, resolvedActionId, {
        [resolvedKey]: value,
      }) as Record<string, unknown>;
      applyBackendUrl(result);
      await load(true);
    } catch (error) {
      reportSimpleError(error);
    }
  }, [applyBackendUrl, extensionId, fieldState, load, reportSimpleError]);

  const runModelMenuAction = useCallback(async (
    template: Record<string, unknown>,
    modelId: string,
  ) => {
    const actionId = String(template?.action_id || '').trim();
    if (!actionId) return;

    const busyKey = `${actionId}:${modelId}`;
    setBusyModelActionKey(busyKey);
    setOpenModelMenuId('');
    setOpenModelMenuPos(null);

    try {
      const result = await runTabAction({
        actionId,
        labelSource: template,
        confirmMessage: template?.confirm,
        payloadKeys: template?.payload_keys,
        payloadOverrides: { selected_model: modelId },
        trackPrimaryBusy: false,
        notify: false,
      });

      if (!result) return;

      if (actionId === 'show_model' && isRuntimeModelDetailsForModal(result.details)) {
        setActionDetails(normalizeModelDetailsForModal(result.details, modelId));
      } else if (isRuntimeModelDetailsForModal(result.details)) {
        setActionDetails(result.details as Record<string, unknown>);
      }
    } finally {
      setBusyModelActionKey('');
    }
  }, [
    isRuntimeModelDetailsForModal,
    normalizeModelDetailsForModal,
    runTabAction,
    setActionDetails,
    setBusyModelActionKey,
    setOpenModelMenuId,
    setOpenModelMenuPos,
  ]);

  const runDeleteModel = useCallback(async (
    deleteTemplate: Record<string, unknown>,
    modelId: string,
    onDeleted?: () => void,
  ) => {
    const actionId = String(deleteTemplate?.action_id || '').trim();
    if (!actionId) return;

    const busyKey = `delete_model:${modelId}`;
    setBusyModelActionKey(busyKey);

    try {
      const result = await runTabAction({
        actionId,
        labelSource: deleteTemplate,
        confirmMessage: deleteTemplate?.confirm,
        payloadKeys: ['selected_model'],
        payloadOverrides: { selected_model: modelId },
        trackPrimaryBusy: false,
        notify: false,
        silentLoad: false,
      });

      if (result?.ok !== false) {
        onDeleted?.();
      }
    } finally {
      setBusyModelActionKey('');
    }
  }, [runTabAction, setBusyModelActionKey]);

  return {
    handleAction,
    handleContentAction,
    runAutosave,
    runModelMenuAction,
    runDeleteModel,
    beginAction,
    reportOutcome,
  };
}
