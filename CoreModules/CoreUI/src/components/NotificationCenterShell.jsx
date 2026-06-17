import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import Card from './Card';
import CoreUIButton from './CoreUIButton';
import CoreUINotificationActionButton from './CoreUINotificationActionButton';
import { notificationModuleLabel } from './notificationModuleLabels';
import { useNotificationCenter } from './NotificationCenterContext';
import { formatElapsedMs, parseTimeMs } from '../utils/elapsedTime';
import '../styles/components/NotificationCenter.css';

function notificationDisplayTitle(notification) {
  const title = notification?.title || '';
  const count = Number(notification?.occurrence_count || 1);
  return count > 1 ? `${title} (${count})` : title;
}

function notificationSortValue(notification) {
  return Date.parse(notification?.last_occurrence_at || notification?.created_at || '') || 0;
}

function notificationDisplayTime(notification) {
  const raw = notification?.last_occurrence_at || notification?.created_at || '';
  const value = Date.parse(raw);
  if (!Number.isFinite(value)) return '';
  return new Intl.DateTimeFormat(undefined, {
    hour: '2-digit',
    minute: '2-digit',
  }).format(new Date(value));
}

function notificationMetadata(notification) {
  const meta = notification?.metadata;
  return meta && typeof meta === 'object' && !Array.isArray(meta) ? meta : {};
}

function notificationNeedsLiveTimer(notification) {
  const meta = notificationMetadata(notification);
  const startedAt = parseTimeMs(meta.started_at || meta.action_started_at);
  const hasDuration = Number.isFinite(Number(meta.duration_ms ?? meta.elapsed_ms));
  const completedAt = parseTimeMs(meta.completed_at || meta.action_completed_at);
  return startedAt != null && !hasDuration && completedAt == null && notification?.kind === 'loading';
}

function notificationTimerInfo(notification, nowMs) {
  const meta = notificationMetadata(notification);
  const durationMs = Number(meta.duration_ms ?? meta.elapsed_ms);
  if (Number.isFinite(durationMs)) {
    return { label: 'Duration', value: formatElapsedMs(durationMs) };
  }
  const startedAt = parseTimeMs(meta.started_at || meta.action_started_at);
  if (startedAt == null) return null;
  const completedAt = parseTimeMs(meta.completed_at || meta.action_completed_at);
  const endMs = completedAt ?? nowMs;
  if (endMs < startedAt) return null;
  return {
    label: completedAt == null ? 'Elapsed' : 'Duration',
    value: formatElapsedMs(endMs - startedAt),
  };
}

function NotificationTimer({ notification, nowMs }) {
  const info = notificationTimerInfo(notification, nowMs);
  if (!info) return null;
  return (
    <div className="notification-center-card-timer">
      <span className="material-symbols-outlined" aria-hidden="true">timer</span>
      <span>{info.label}</span>
      <strong>{info.value}</strong>
    </div>
  );
}

function ModuleFooter({ source, notification }) {
  return (
    <div className="notification-center-module-footer">
      <span className="notification-center-module-footer-source">
        {notificationModuleLabel(source)}
      </span>
      <span className="notification-center-module-footer-time">
        {notificationDisplayTime(notification)}
      </span>
    </div>
  );
}

function FormattedMessage({ text }) {
  if (!text) return null;
  return text.split('\n').map((line, i) => {
    const dotMatch = line.match(/^●\s+(.*)/);
    return (
      <div key={i}>
        {dotMatch ? <><span className="notification-changelog-dot" />{dotMatch[1]}</> : line}
      </div>
    );
  });
}

const NOTIFICATION_SCROLL_BOTTOM_THRESHOLD_PX = 8;

function isNotificationScrollAtBottom(scrollEl) {
  if (!scrollEl) return true;
  const distanceFromBottom = scrollEl.scrollHeight - scrollEl.clientHeight - scrollEl.scrollTop;
  return distanceFromBottom <= NOTIFICATION_SCROLL_BOTTOM_THRESHOLD_PX;
}

function scrollNotificationListToLatest(scrollEl, behavior = 'auto') {
  if (!scrollEl) return;
  const top = Math.max(0, scrollEl.scrollHeight - scrollEl.clientHeight);
  if (behavior === 'auto') {
    scrollEl.scrollTop = top;
    return;
  }
  scrollEl.scrollTo({ top, behavior });
}

function NotificationCenterShell({ onOpenRagRunDetails = null }) {
  const {
    sessionId,
    persisted,
    liveActivities,
    dismissPersisted,
    dismissPersistedMany,
    clearPersisted,
    suppressLiveActivity,
  } = useNotificationCenter();
  const [menuOpen, setMenuOpen] = useState(false);
  const [nowMs, setNowMs] = useState(Date.now());
  const [leavingPersistedIds, setLeavingPersistedIds] = useState(() => new Set());
  const [leavingLiveIds, setLeavingLiveIds] = useState(() => new Set());
  const [leavingHistoryIds, setLeavingHistoryIds] = useState(() => new Set());
  const [clearLeaving, setClearLeaving] = useState(false);
  const [clearBatchIds, setClearBatchIds] = useState(() => []);
  const [clearBatchLiveIds, setClearBatchLiveIds] = useState(() => []);
  const [historyLeaving, setHistoryLeaving] = useState(false);
  const rootRef = useRef(null);
  const scrollRef = useRef(null);
  const stickToBottomRef = useRef(true);
  const [showLatestAction, setShowLatestAction] = useState(false);

  useEffect(() => {
    if (!menuOpen) return undefined;
    const onDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) {
        setMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [menuOpen]);

  const hasRunningPersistedTimer = persisted.some(notificationNeedsLiveTimer);

  useEffect(() => {
    if (!hasRunningPersistedTimer) return undefined;
    setNowMs(Date.now());
    const id = setInterval(() => setNowMs(Date.now()), 1000);
    return () => clearInterval(id);
  }, [hasRunningPersistedTimer]);

  const activePersisted = sessionId
    ? persisted.filter((n) => !n.dismissed_at && !n.metadata?.historyOnly)
    : [];
  const visiblePersisted = persisted.filter(
    (n) => (
      !n.metadata?.historyOnly
      && (!n.dismissed_at || leavingPersistedIds.has(n.id))
    ),
  );
  const history = [...persisted].sort((a, b) => notificationSortValue(b) - notificationSortValue(a));

  const liveEntries = [...liveActivities.entries()];
  const visibleLiveEntries = liveEntries.concat(
    [...leavingLiveIds]
      .filter((id) => !liveActivities.has(id))
      .map((id) => [id, liveActivities.get(id) || { source: 'system', node: null, headerLeading: null }]),
  );
  const hasVisibleCards = activePersisted.length > 0 || liveEntries.length > 0;
  const visibleCardSignature = `${visiblePersisted.length}:${visibleLiveEntries.length}`;

  const updateScrollState = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = isNotificationScrollAtBottom(el);
    const canScroll = el.scrollHeight > el.clientHeight + 1;
    stickToBottomRef.current = atBottom;
    setShowLatestAction(canScroll && !atBottom);
  }, []);

  const scrollToLatest = useCallback((behavior = 'smooth') => {
    const el = scrollRef.current;
    if (!el) return;
    scrollNotificationListToLatest(el, behavior);
    stickToBottomRef.current = true;
    setShowLatestAction(false);
  }, []);

  useLayoutEffect(() => {
    scrollNotificationListToLatest(scrollRef.current, 'auto');
    updateScrollState();
  }, [updateScrollState]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return undefined;

    const onScroll = () => updateScrollState();
    el.addEventListener('scroll', onScroll, { passive: true });

    const resizeObserver = new ResizeObserver(() => {
      if (stickToBottomRef.current) {
        scrollNotificationListToLatest(el, 'auto');
      }
      updateScrollState();
    });
    resizeObserver.observe(el);
    if (el.firstElementChild) {
      resizeObserver.observe(el.firstElementChild);
    }

    return () => {
      el.removeEventListener('scroll', onScroll);
      resizeObserver.disconnect();
    };
  }, [updateScrollState]);

  useLayoutEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    if (stickToBottomRef.current) {
      scrollNotificationListToLatest(el, 'auto');
    }
    updateScrollState();
  }, [visibleCardSignature, updateScrollState]);

  const handleDismissPersisted = (id) => {
    setLeavingPersistedIds((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  };

  const finalizePersistedDismiss = (id) => {
    void dismissPersisted(id);
  };

  const handleClearVisible = () => {
    const persistedIds = activePersisted.map((n) => n.id);
    const liveIds = liveEntries.map(([id]) => id);
    setLeavingPersistedIds((prev) => {
      const next = new Set(prev);
      persistedIds.forEach((id) => next.add(id));
      return next;
    });
    setLeavingLiveIds((prev) => {
      const next = new Set(prev);
      liveIds.forEach((id) => next.add(id));
      return next;
    });
    setClearLeaving(true);
    setClearBatchIds(persistedIds);
    setClearBatchLiveIds(liveIds);
  };

  const finalizeClearVisible = () => {
    if (clearBatchIds.length > 0) {
      void dismissPersistedMany(clearBatchIds);
    }
    clearBatchLiveIds.forEach((id) => suppressLiveActivity(id));
    setClearBatchIds([]);
    setClearBatchLiveIds([]);
  };

  const handleLiveClose = (id) => {
    setLeavingLiveIds((prev) => {
      if (prev.has(id)) return prev;
      const next = new Set(prev);
      next.add(id);
      return next;
    });
  };

  const finalizeLiveClose = (id) => {
    suppressLiveActivity(id);
  };

  const handlePersistedLeaveEnd = (id) => {
    setLeavingPersistedIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    if (clearBatchIds.length === 0 || !clearBatchIds.includes(id)) {
      finalizePersistedDismiss(id);
    }
  };

  const handleLiveLeaveEnd = (id) => {
    setLeavingLiveIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    if (clearBatchLiveIds.length === 0 || !clearBatchLiveIds.includes(id)) {
      finalizeLiveClose(id);
    }
  };

  const handleClearLeaveEnd = () => {
    setClearLeaving(false);
    finalizeClearVisible();
  };

  const handleClearHistory = () => {
    const ids = history.map((n) => n.id);
    setLeavingHistoryIds((prev) => {
      const next = new Set(prev);
      ids.forEach((id) => next.add(id));
      return next;
    });
    setHistoryLeaving(true);
  };

  const handleHistoryRowLeaveEnd = (id) => {
    setLeavingHistoryIds((prev) => {
      if (!prev.has(id)) return prev;
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
  };

  const handleHistoryPopoverLeaveEnd = () => {
    setHistoryLeaving(false);
    void clearPersisted();
  };

  useEffect(() => {
    if (leavingPersistedIds.size === 0) return undefined;
    const timers = [];
    leavingPersistedIds.forEach((id) => {
      const timer = setTimeout(() => handlePersistedLeaveEnd(id), 600);
      timers.push(timer);
    });
    return () => timers.forEach((t) => clearTimeout(t));
  }, [leavingPersistedIds]);

  useEffect(() => {
    if (leavingLiveIds.size === 0) return undefined;
    const timers = [];
    leavingLiveIds.forEach((id) => {
      const timer = setTimeout(() => handleLiveLeaveEnd(id), 600);
      timers.push(timer);
    });
    return () => timers.forEach((t) => clearTimeout(t));
  }, [leavingLiveIds]);

  useEffect(() => {
    if (!clearLeaving) return undefined;
    const timer = setTimeout(() => handleClearLeaveEnd(), 600);
    return () => clearTimeout(timer);
  }, [clearLeaving]);

  useEffect(() => {
    if (!historyLeaving) return undefined;
    const timer = setTimeout(() => handleHistoryPopoverLeaveEnd(), 500);
    return () => clearTimeout(timer);
  }, [historyLeaving]);

  useEffect(() => {
    if (leavingHistoryIds.size === 0) return undefined;
    const timers = [];
    leavingHistoryIds.forEach((id) => {
      const timer = setTimeout(() => handleHistoryRowLeaveEnd(id), 600);
      timers.push(timer);
    });
    return () => timers.forEach((t) => clearTimeout(t));
  }, [leavingHistoryIds]);

  const extractRagRunId = (notification) => {
    const meta = notification?.metadata && typeof notification.metadata === 'object'
      ? notification.metadata
      : null;
    const rid = meta?.run_id || meta?.rag_run_id || meta?.runId || '';
    return String(rid || '').trim();
  };

  const openRagRunResults = (runId) => {
    if (!runId) return;
    if (typeof onOpenRagRunDetails === 'function') onOpenRagRunDetails(runId);
  };

  if (!sessionId) return null;

  return (
    <div className="notification-center-root" ref={rootRef}>
      {(menuOpen || historyLeaving) && (
        <div
          className={`notification-center-popover${historyLeaving ? ' notification-center-popover--leaving' : ''}`}
          role="dialog"
          aria-label="Notification history"
          onAnimationEnd={historyLeaving ? handleHistoryPopoverLeaveEnd : undefined}
        >
          <div className="notification-center-popover-header">
            <span className="notification-center-popover-title">History</span>
            <CoreUIButton
              size="sm"
              variant="ghost"
              onClick={handleClearHistory}
              disabled={historyLeaving}
            >
              Clear
            </CoreUIButton>
          </div>
          <div className="notification-center-popover-list">
            {history.length === 0 ? (
              <p className="notification-center-popover-empty">No entries yet.</p>
            ) : (
              history.map((n) => {
                const isRowLeaving = leavingHistoryIds.has(n.id);
                return (
                  <div
                    key={n.id}
                    className={`notification-center-popover-row notification-center-popover-row--${n.kind || 'event'}${isRowLeaving ? ' notification-center-popover-row--leaving' : ''}`}
                    onAnimationEnd={isRowLeaving ? () => handleHistoryRowLeaveEnd(n.id) : undefined}
                  >
                    <div className="notification-center-popover-row-main">
                    <div className="notification-center-popover-row-title">{notificationDisplayTitle(n)}</div>
                    {n.message ? (
                      <div className="notification-center-popover-row-msg"><FormattedMessage text={n.message} /></div>
                    ) : null}
                    <NotificationTimer notification={n} nowMs={nowMs} />
                  </div>
                  <ModuleFooter source={n.source} notification={n} />
                </div>
                );
              })
            )}
          </div>
        </div>
      )}

      <div className="notification-center-scroll" ref={scrollRef}>
        <div className="notification-center-stack" aria-live="polite">
        {visiblePersisted.map((n) => {
          const isLeaving = leavingPersistedIds.has(n.id);
          return (
          <Card
            key={`p-${n.id}`}
            className={`notification-center-card notification-center-card--${n.kind || 'event'}${isLeaving ? ' notification-center-card--leaving' : ''}`}
            elevation="var(--md-sys-elevation-level2)"
            role="status"
            onAnimationEnd={isLeaving ? () => handlePersistedLeaveEnd(n.id) : undefined}
          >
            <div className="notification-center-card-header">
              {n.kind === 'loading' && (
                <span className="notification-center-card-spinner" aria-hidden="true" />
              )}
              <span className="notification-center-card-header-title">{notificationDisplayTitle(n)}</span>
              <button
                type="button"
                className="notification-center-card-close"
                aria-label="Dismiss notification"
                onClick={() => handleDismissPersisted(n.id)}
              >
                ×
              </button>
            </div>
            <div className="notification-center-card-main">
{n.message ? (
                <div className="notification-center-card-message"><FormattedMessage text={n.message} /></div>
              ) : null}
              {n.source === 'rag-tests' && extractRagRunId(n) ? (
                <div className="notification-center-card-actions">
                  <button
                    type="button"
                    className="notification-center-card-action-btn"
                    onClick={() => {
                      openRagRunResults(extractRagRunId(n));
                    }}
                  >
                    View results
                  </button>
                </div>
              ) : null}
              <NotificationTimer notification={n} nowMs={nowMs} />
            </div>
            <ModuleFooter source={n.source} notification={n} />
          </Card>
          );
        })}

        {visibleLiveEntries.map(([id, { source, node, headerLeading }]) => {
          const isLiveLeaving = leavingLiveIds.has(id);
          return (
          <Card
            key={`l-${id}`}
            className={`notification-center-card notification-center-card--live${isLiveLeaving ? ' notification-center-card--leaving' : ''}`}
            elevation="var(--md-sys-elevation-level2)"
            role="status"
            onAnimationEnd={isLiveLeaving ? () => handleLiveLeaveEnd(id) : undefined}
          >
            <div className="notification-center-card-header">
              <span
                className={`notification-center-card-header-title${
                  headerLeading ? ' notification-center-card-header-title--with-leading' : ''
                }`}
              >
                {headerLeading}
                <span className="notification-center-card-header-title-text">
                  {notificationModuleLabel(source)}
                </span>
              </span>
              <button
                type="button"
                className="notification-center-card-close"
                aria-label="Close notification"
                onClick={() => {
                  setLeavingLiveIds((prev) => {
                    if (prev.has(id)) return prev;
                    const next = new Set(prev);
                    next.add(id);
                    return next;
                  });
                  suppressLiveActivity(id);
                }}
              >
                ×
              </button>
            </div>
            <div className="notification-center-card-live-slot">{node}</div>
            <ModuleFooter source={source} />
          </Card>
          );
        })}
        </div>
      </div>

      <div className="notification-center-actions-row">
        {showLatestAction ? (
          <CoreUINotificationActionButton
            icon="keyboard_arrow_down"
            label="Latest"
            onClick={() => scrollToLatest('smooth')}
            title="Scroll to latest notifications"
          />
        ) : null}
        {hasVisibleCards ? (
          <CoreUINotificationActionButton
            icon="cleaning_services"
            label="Clear"
            onClick={handleClearVisible}
            className={clearLeaving ? 'coreui-notification-action-btn--leaving' : undefined}
            onAnimationEnd={clearLeaving ? handleClearLeaveEnd : undefined}
          />
        ) : null}
        <CoreUINotificationActionButton
          icon="notifications"
          label="Notifications"
          onClick={() => setMenuOpen((o) => !o)}
          expanded={menuOpen}
          hasPopup="dialog"
        />
      </div>
    </div>
  );
}

export default NotificationCenterShell;
