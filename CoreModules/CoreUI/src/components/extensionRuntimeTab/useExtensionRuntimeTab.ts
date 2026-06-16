import { useCallback, useEffect, useRef, useState } from 'react';
import { getExtensionTab, refreshExtensionTab } from '../../services/api';
import { extensionTabPayloadsEqual, fieldStatesEqual } from './comparePayload';
import {
  extractContentFieldDefaults,
  extractFieldDefaults,
  hasRenderableExtensionPayload,
  isExtensionTabTerminalError,
  isExtensionTabWaiting,
  isRuntimeStillLoadingMessage,
} from './extensionRuntimeTabUtils';

type ErrorState = boolean | 'loading';

export function useExtensionRuntimeTab(
  extensionId: string,
  onErrorStateChange?: (state: ErrorState) => void,
) {
  const [payload, setPayload] = useState<Record<string, unknown> | null>(null);
  const [fieldState, setFieldState] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runtimeLoadingMessage, setRuntimeLoadingMessage] = useState('');
  const [loadStartedAt, setLoadStartedAt] = useState(() => Date.now());
  const [loadTimerNow, setLoadTimerNow] = useState(() => Date.now());
  const [refreshKey, setRefreshKey] = useState(0);

  const onErrorStateChangeRef = useRef(onErrorStateChange);
  const lastErrorStateRef = useRef<ErrorState>(false);
  const refreshRequestedRef = useRef('');

  useEffect(() => {
    onErrorStateChangeRef.current = onErrorStateChange;
  }, [onErrorStateChange]);

  useEffect(() => {
    refreshRequestedRef.current = '';
  }, [extensionId]);

  const load = useCallback(async (silent = false) => {
    if (!silent) {
      const startedAt = Date.now();
      setLoadStartedAt(startedAt);
      setLoadTimerNow(startedAt);
      setLoading(true);
    }
    setError(null);
    setRuntimeLoadingMessage('');
    try {
      const data = await getExtensionTab(extensionId) as Record<string, unknown>;
      setPayload((prev) => (extensionTabPayloadsEqual(prev, data) ? prev : data));
      setFieldState((prev) => {
        const next = {
          ...extractFieldDefaults(data?.schema),
          ...extractContentFieldDefaults(data?.content),
          ...prev,
        };
        return fieldStatesEqual(prev, next) ? prev : next;
      });
      const nextState: ErrorState = isExtensionTabWaiting(data) && !hasRenderableExtensionPayload(data)
        ? 'loading'
        : isExtensionTabTerminalError(data)
          ? true
          : false;
      if (lastErrorStateRef.current !== nextState) {
        lastErrorStateRef.current = nextState;
        onErrorStateChangeRef.current?.(nextState);
      }
    } catch (e) {
      const msg = String((e as Error)?.message || e);
      const nextState: ErrorState = isRuntimeStillLoadingMessage(msg) ? 'loading' : true;
      if (nextState === 'loading') {
        setRuntimeLoadingMessage(msg);
      } else {
        setError(msg);
      }
      if (lastErrorStateRef.current !== nextState) {
        lastErrorStateRef.current = nextState;
        onErrorStateChangeRef.current?.(nextState);
      }
    } finally {
      if (!silent) setLoading(false);
    }
  }, [extensionId]);

  useEffect(() => {
    void load();
  }, [load]);

  const loadState = (payload?.load_state || null) as Record<string, unknown> | null;
  const loadStatus = String(loadState?.status || '').trim().toLowerCase();
  const waitingForTabPayload = isExtensionTabWaiting(payload);
  const hasRenderablePayload = hasRenderableExtensionPayload(payload);

  useEffect(() => {
    if (!loading && !runtimeLoadingMessage && !waitingForTabPayload) return undefined;
    setLoadTimerNow(Date.now());
    const id = setInterval(() => setLoadTimerNow(Date.now()), 1000);
    return () => clearInterval(id);
  }, [loading, runtimeLoadingMessage, waitingForTabPayload]);

  useEffect(() => {
    if (!runtimeLoadingMessage) return undefined;
    const id = setInterval(() => { void load(true); }, 2000);
    return () => clearInterval(id);
  }, [runtimeLoadingMessage, load]);

  useEffect(() => {
    if (!waitingForTabPayload) return undefined;
    const refreshKeyValue = loadStatus === 'refreshing'
      ? `${extensionId}:refreshing:${loadState?.job_id || ''}`
      : `${extensionId}:${loadStatus || 'missing'}:${loadState?.finished_at || loadState?.job_id || ''}`;
    if (loadStatus !== 'refreshing' && refreshRequestedRef.current !== refreshKeyValue) {
      refreshRequestedRef.current = refreshKeyValue;
      void refreshExtensionTab(extensionId).catch((e) => {
        const msg = String((e as Error)?.message || e);
        setError(msg);
        onErrorStateChangeRef.current?.(true);
      });
    }
    const id = setInterval(() => { void load(true); }, hasRenderablePayload ? 2500 : 1500);
    return () => clearInterval(id);
  }, [
    extensionId,
    hasRenderablePayload,
    load,
    loadState?.finished_at,
    loadState?.job_id,
    loadStatus,
    waitingForTabPayload,
  ]);

  return {
    payload,
    fieldState,
    setFieldState,
    loading,
    error,
    runtimeLoadingMessage,
    loadStartedAt,
    loadTimerNow,
    refreshKey,
    setRefreshKey,
    load,
    loadState,
    loadStatus,
    waitingForTabPayload,
    hasRenderablePayload,
  };
}
