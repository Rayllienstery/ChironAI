import React, {
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
  const [liveMap, setLiveMap] = useState(() => new Map());
  const liveMapRef = useRef(liveMap);
  liveMapRef.current = liveMap;

  const refreshPersisted = useCallback(async () => {
    if (!sessionId) {
      setPersisted([]);
      return;
    }
    try {
      const data = await getCoreuiNotifications(sessionId, { includeDismissed: true, limit: 200 });
      setPersisted(data.notifications || []);
    } catch (e) {
      console.error('NotificationCenter: failed to load', e);
    }
  }, [sessionId]);

  useEffect(() => {
    refreshPersisted();
  }, [refreshPersisted]);

  const setLiveActivity = useCallback((id, source, node) => {
    if (id == null || id === '') return;
    setLiveMap((prev) => {
      const next = new Map(prev);
      next.set(String(id), { source, node });
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

  const persistNotification = useCallback(
    async (payload) => {
      if (!sessionId) return null;
      try {
        const data = await createCoreuiNotification(sessionId, payload);
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
      try {
        await dismissCoreuiNotification(sessionId, notificationId);
        await refreshPersisted();
      } catch (e) {
        console.error('NotificationCenter: dismiss failed', e);
      }
    },
    [sessionId, refreshPersisted],
  );

  const clearPersisted = useCallback(async () => {
    if (!sessionId) return;
    try {
      await clearCoreuiNotifications(sessionId);
      await refreshPersisted();
    } catch (e) {
      console.error('NotificationCenter: clear failed', e);
    }
  }, [sessionId, refreshPersisted]);

  const value = useMemo(
    () => ({
      sessionId,
      persisted,
      liveActivities: liveMap,
      refreshPersisted,
      setLiveActivity,
      clearLiveActivity,
      persistNotification,
      dismissPersisted,
      clearPersisted,
    }),
    [
      sessionId,
      persisted,
      liveMap,
      refreshPersisted,
      setLiveActivity,
      clearLiveActivity,
      persistNotification,
      dismissPersisted,
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
