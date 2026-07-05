import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import {
  clearCoreuiNotifications,
  createCoreuiNotification,
  dismissCoreuiNotification,
  getCoreuiNotifications,
} from '../services/api';

const NotificationCenterContext = createContext(undefined);

export function NotificationCenterProvider({ sessionId, children }) {
  const [persisted, setPersisted] = useState([]);
  const [persistedLoaded, setPersistedLoaded] = useState(false);
  const [liveMap, setLiveMap] = useState(() => new Map());
  const [liveSuppressedIds, setLiveSuppressedIds] = useState(() => []);
  const liveMapRef = useRef(liveMap);
  liveMapRef.current = liveMap;

  const refreshPersisted = useCallback(async () => {
    if (!sessionId) {
      setPersisted([]);
      setPersistedLoaded(true);
      return;
    }
    setPersistedLoaded(false);
    try {
      const data = await getCoreuiNotifications(sessionId, { includeDismissed: true, limit: 200 });
      setPersisted(data.notifications || []);
    } catch (e) {
      console.error('NotificationCenter: failed to load', e);
    } finally {
      setPersistedLoaded(true);
    }
  }, [sessionId]);

  useEffect(() => {
    refreshPersisted();
  }, [refreshPersisted]);

  const setLiveActivity = useCallback((id, source, node, options) => {
    if (id == null || id === '') return;
    const headerLeading = options && options.headerLeading != null ? options.headerLeading : null;
    setLiveMap((prev) => {
      const next = new Map(prev);
      next.set(String(id), { source, node, headerLeading });
      return next;
    });
  }, []);

  const clearLiveActivity = useCallback((id) => {
    if (id == null || id === '') return;
    setLiveMap((prev) => {
      const next = new Map(prev);
      next.delete(String(id));
      return next;
    });
  }, []);

  const suppressLiveActivity = useCallback((id) => {
    if (id == null || id === '') return;
    const sid = String(id);
    setLiveMap((prev) => {
      const next = new Map(prev);
      next.delete(sid);
      return next;
    });
    setLiveSuppressedIds((prev) => (prev.includes(sid) ? prev : [...prev, sid]));
  }, []);

  const clearLiveSuppression = useCallback((id) => {
    if (id == null || id === '') return;
    const sid = String(id);
    setLiveSuppressedIds((prev) => prev.filter((x) => x !== sid));
  }, []);

  const persistNotification = useCallback(
    async (payload) => {
      if (!sessionId) return null;
      try {
        const data = await createCoreuiNotification(sessionId, {
          ...payload,
          is_console_error: payload.is_console_error || false,
        });
        await refreshPersisted();
        return data?.id ?? null;
      } catch (e) {
        console.error('NotificationCenter: persist failed', e);
        return null;
      }
    },
    [sessionId, refreshPersisted],
  );

  const dismissPersisted = useCallback(
    async (notificationId) => {
      if (!sessionId) return;
      const dismissedAt = new Date().toISOString();
      setPersisted((prev) =>
        prev.map((item) => (
          item.id === notificationId ? { ...item, dismissed_at: item.dismissed_at || dismissedAt } : item
        )),
      );
      try {
        await dismissCoreuiNotification(sessionId, notificationId);
      } catch (e) {
        console.error('NotificationCenter: dismiss failed', e);
        await refreshPersisted();
      }
    },
    [sessionId, refreshPersisted],
  );

  const dismissPersistedMany = useCallback(
    async (notificationIds) => {
      if (!sessionId) return;
      const ids = [...new Set((notificationIds || []).filter((id) => id != null))];
      if (ids.length === 0) return;
      const dismissedAt = new Date().toISOString();
      const idSet = new Set(ids);
      setPersisted((prev) =>
        prev.map((item) => (
          idSet.has(item.id) ? { ...item, dismissed_at: item.dismissed_at || dismissedAt } : item
        )),
      );
      const results = await Promise.allSettled(
        ids.map((id) => dismissCoreuiNotification(sessionId, id)),
      );
      if (results.some((result) => result.status === 'rejected')) {
        console.error('NotificationCenter: bulk dismiss had failures');
        await refreshPersisted();
      }
    },
    [sessionId, refreshPersisted],
  );

  const clearPersisted = useCallback(async () => {
    if (!sessionId) return;
    // Optimistically empty the UI immediately; delete from DB in the background.
    setPersisted([]);
    try {
      await clearCoreuiNotifications(sessionId);
    } catch (e) {
      console.error('NotificationCenter: clear failed', e);
      // Refresh on failure to avoid losing notifications that arrived while clearing.
      await refreshPersisted();
    }
  }, [sessionId, refreshPersisted]);

  const value = useMemo(
    () => ({
      sessionId,
      persisted,
      persistedLoaded,
      liveActivities: liveMap,
      liveSuppressedIds,
      refreshPersisted,
      setLiveActivity,
      clearLiveActivity,
      suppressLiveActivity,
      clearLiveSuppression,
      persistNotification,
      dismissPersisted,
      dismissPersistedMany,
      clearPersisted,
    }),
    [
      sessionId,
      persisted,
      persistedLoaded,
      liveMap,
      liveSuppressedIds,
      refreshPersisted,
      setLiveActivity,
      clearLiveActivity,
      suppressLiveActivity,
      clearLiveSuppression,
      persistNotification,
      dismissPersisted,
      dismissPersistedMany,
      clearPersisted,
    ],
  );

  return (
    <NotificationCenterContext.Provider value={value}>{children}</NotificationCenterContext.Provider>
  );
}

export function useNotificationCenter() {
  const ctx = useContext(NotificationCenterContext);
  if (!ctx) {
    throw new Error('useNotificationCenter must be used within NotificationCenterProvider');
  }
  return ctx;
}

/** Returns null if there is no provider (e.g. isolated tests). */
export function useOptionalNotificationCenter() {
  return useContext(NotificationCenterContext);
}
