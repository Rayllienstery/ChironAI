import React, { useEffect, useRef, useState } from 'react';
import Card from './Card';
import { notificationModuleLabel } from './notificationModuleLabels';
import { useNotificationCenter } from './NotificationCenterContext';
import '../styles/components/CoreUIButtons.css';
import '../styles/components/NotificationCenter.css';

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

function ModuleFooter({ source }) {
  return (
    <div className="notification-center-module-footer">
      {notificationModuleLabel(source)}
    </div>
  );
}

function NotificationCenterShell() {
  const {
    sessionId,
    persisted,
    liveActivities,
    dismissPersisted,
    clearPersisted,
    suppressLiveActivity,
  } = useNotificationCenter();
  const [menuOpen, setMenuOpen] = useState(false);
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

  if (!sessionId) return null;

  const activePersisted = persisted.filter(
    (n) => !n.dismissed_at && !n.metadata?.historyOnly,
  );
  const history = [...persisted].sort((a, b) => (b.id ?? 0) - (a.id ?? 0));

  const liveEntries = [...liveActivities.entries()];

  return (
    <div className="notification-center-root" ref={rootRef}>
      {menuOpen && (
        <div className="notification-center-popover" role="dialog" aria-label="Notification history">
          <div className="notification-center-popover-header">
            <span className="notification-center-popover-title">History</span>
            <button
              type="button"
              className="coreui-btn coreui-btn-small coreui-btn-ghost"
              onClick={() => {
                clearPersisted();
              }}
            >
              Clear
            </button>
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
                    <div className="notification-center-popover-row-title">{n.title}</div>
                    {n.message ? (
                      <div className="notification-center-popover-row-msg">{n.message}</div>
                    ) : null}
                    <div className="notification-center-popover-row-meta">
                      <span className="notification-center-popover-row-time">
                        {n.created_at ? String(n.created_at).replace('T', ' ').slice(0, 19) : ''}
                      </span>
                    </div>
                  </div>
                  <ModuleFooter source={n.source} />
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
              <span className="notification-center-card-header-title">{n.title}</span>
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
                <div className="notification-center-card-message">{n.message}</div>
              ) : null}
            </div>
            <ModuleFooter source={n.source} />
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
  );
}

export default NotificationCenterShell;
