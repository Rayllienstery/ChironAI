import { useEffect, useRef, useState } from 'react';
import Card from './Card';
import CoreUIButton from './CoreUIButton';
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

function BellIcon() {
  return (
    <svg
      className="notification-center-bell-svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      aria-hidden="true"
      fill="currentColor"
    >
      <path d="M12 22c1.1 0 2-.9 2-2h-4c0 1.1.89 2 2 2zm6-6v-5c0-3.07-1.64-5.64-4.5-6.32V4c0-.83-.67-1.5-1.5-1.5s-1.5.67-1.5 1.5v.68C7.63 5.36 6 7.92 6 11v5l-2 2v1h16v-1l-2-2z" />
    </svg>
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

function BroomIcon() {
  return (
    <svg
      className="notification-center-broom-svg"
      width="18"
      height="18"
      viewBox="0 0 24 24"
      aria-hidden="true"
      fill="currentColor"
    >
      <path d="M18.68 3.32a1 1 0 0 0-1.41 0l-4.95 4.95a1 1 0 0 0 0 1.41l.35.35-7.78 7.78a3 3 0 0 0-.83 1.54l-.34 1.69a.75.75 0 0 0 .88.88l1.69-.34a3 3 0 0 0 1.54-.83l7.78-7.78.35.35a1 1 0 0 0 1.41 0l4.95-4.95a1 1 0 0 0 0-1.41zm-12.2 16.16a1.5 1.5 0 0 1-.77.42l-.74.15.15-.74a1.5 1.5 0 0 1 .42-.77l7.78-7.78 1.06 1.06z" />
    </svg>
  );
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
  const rootRef = useRef(null);

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

  if (!sessionId) return null;

  const activePersisted = persisted.filter(
    (n) => !n.dismissed_at && !n.metadata?.historyOnly,
  );
  const history = [...persisted].sort((a, b) => notificationSortValue(b) - notificationSortValue(a));

  const liveEntries = [...liveActivities.entries()];
  const hasVisibleCards = activePersisted.length > 0 || liveEntries.length > 0;

  const handleClearVisible = () => {
    void dismissPersistedMany(activePersisted.map((n) => n.id));
    liveEntries.forEach(([id]) => suppressLiveActivity(id));
  };

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

  return (
    <div className="notification-center-root" ref={rootRef}>
      {menuOpen && (
        <div className="notification-center-popover" role="dialog" aria-label="Notification history">
          <div className="notification-center-popover-header">
            <span className="notification-center-popover-title">History</span>
            <CoreUIButton
              size="sm"
              variant="ghost"
              onClick={() => {
                clearPersisted();
              }}
            >
              Clear
            </CoreUIButton>
          </div>
          <div className="notification-center-popover-list">
            {history.length === 0 ? (
              <p className="notification-center-popover-empty">No entries yet.</p>
            ) : (
              history.map((n) => (
                <div
                  key={n.id}
                  className={`notification-center-popover-row notification-center-popover-row--${n.kind || 'event'}`}
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
              ))
            )}
          </div>
        </div>
      )}

      <div className="notification-center-stack" aria-live="polite">
        {activePersisted.map((n) => (
          <Card
            key={`p-${n.id}`}
            className={`notification-center-card notification-center-card--${n.kind || 'event'}`}
            elevation="var(--md-sys-elevation-level2)"
            role="status"
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
                onClick={() => dismissPersisted(n.id)}
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
        ))}

        {liveEntries.map(([id, { source, node, headerLeading }]) => (
          <Card
            key={`l-${id}`}
            className="notification-center-card notification-center-card--live"
            elevation="var(--md-sys-elevation-level2)"
            role="status"
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
                onClick={() => suppressLiveActivity(id)}
              >
                ×
              </button>
            </div>
            <div className="notification-center-card-live-slot">{node}</div>
            <ModuleFooter source={source} />
          </Card>
        ))}
      </div>

      <div className="notification-center-actions-row">
        {hasVisibleCards ? (
          <Card
            as="button"
            type="button"
            className="notification-center-clear-capsule"
            elevation="var(--md-sys-elevation-level3)"
            interactive
            onClick={handleClearVisible}
            aria-label="Clear visible notifications"
            title="Clear visible notifications"
          >
            <BroomIcon />
          </Card>
        ) : null}
        <Card
          as="button"
          type="button"
          className="notification-center-bell-capsule"
          elevation="var(--md-sys-elevation-level3)"
          interactive
          onClick={() => setMenuOpen((o) => !o)}
          aria-expanded={menuOpen}
          aria-haspopup="dialog"
        >
          <BellIcon />
          <span>Notifications</span>
        </Card>
      </div>
    </div>
  );
}

export default NotificationCenterShell;
