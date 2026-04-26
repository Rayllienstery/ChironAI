import { useState, useEffect, useCallback, useMemo } from 'react';
import { getProxyJournal, clearProxyJournal } from '../services/api';
import '../styles/components/DashboardTab.css';
import CoreUIButton from './CoreUIButton';
import ProxyTraceDetailModal from './ProxyTraceDetailModal';

const JOURNAL_LIMIT = 2000;
const JOURNAL_POLL_MS = 3000;

function getDateRangeForJournal(period, selectedDate) {
  const now = new Date();
  if (selectedDate) {
    const d = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate());
    const from = new Date(d);
    from.setHours(0, 0, 0, 0);
    const to = new Date(d);
    to.setHours(23, 59, 59, 999);
    return { from: from.toISOString(), to: to.toISOString() };
  }
  switch (period) {
    case 'day': {
      const start = new Date(now);
      start.setHours(0, 0, 0, 0);
      return { from: start.toISOString(), to: now.toISOString() };
    }
    case 'week': {
      const start = new Date(now);
      start.setDate(start.getDate() - 6);
      start.setHours(0, 0, 0, 0);
      return { from: start.toISOString(), to: now.toISOString() };
    }
    case 'month': {
      const start = new Date(now.getFullYear(), now.getMonth(), 1);
      return { from: start.toISOString(), to: now.toISOString() };
    }
    case 'year': {
      const start = new Date(now.getFullYear(), 0, 1);
      return { from: start.toISOString(), to: now.toISOString() };
    }
    default:
      return {};
  }
}

function readMetadata(log) {
  if (!log || !log.metadata) return {};
  if (typeof log.metadata === 'string') {
    try {
      return JSON.parse(log.metadata);
    } catch {
      return {};
    }
  }
  return log.metadata;
}

function hasImage(meta) {
  if (meta.has_image) return true;
  const messages = meta.request?.messages;
  if (Array.isArray(messages)) {
    return messages.some((m) => {
      if (Array.isArray(m.content)) {
        return m.content.some((c) => c.type === 'image' || c.type === 'image_url');
      }
      return false;
    });
  }
  return false;
}

function formatLogMessage(msg, meta) {
  let text = meta?.user_query || '';
  if (!text && msg) {
    // Strip "Proxy request (...): " or "Proxy request: "
    text = msg.replace(/^Proxy request\s*(\([^)]+\))?:\s*/, '');
  }
  if (!text) return '';

  // Remove <environment_details>...</environment_details> tags and their content
  return text.replace(/<environment_details>[\s\S]*?<\/environment_details>/g, '').trim();
}

export default function ProxyJournalTab() {
  const [period, setPeriod] = useState('week');
  const [selectedDate, setSelectedDate] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);

  const loadJournal = useCallback(
    async (opts = {}) => {
      const silent = opts.silent === true;
      if (!silent) {
        setLoading(true);
        setErr(null);
      }
      try {
        const { from, to } = getDateRangeForJournal(period, selectedDate);
        const data = await getProxyJournal({
          limit: JOURNAL_LIMIT,
          from: from || undefined,
          to: to || undefined,
        });
        const rows = data.logs || [];
        setLogs(rows.slice().reverse());
      } catch (e) {
        if (!silent) {
          setErr(String(e.message || e));
          setLogs([]);
        }
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [period, selectedDate],
  );

  useEffect(() => {
    loadJournal();
  }, [loadJournal]);

  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      if (cancelled || document.visibilityState !== 'visible') return;
      loadJournal({ silent: true });
    };
    poll();
    const t = setInterval(poll, JOURNAL_POLL_MS);
    const onVis = () => {
      if (document.visibilityState === 'visible') poll();
    };
    document.addEventListener('visibilitychange', onVis);
    return () => {
      cancelled = true;
      clearInterval(t);
      document.removeEventListener('visibilitychange', onVis);
    };
  }, [loadJournal]);

  const displayLogs = useMemo(() => {
    const byTrace = new Map();
    const noTrace = [];
    for (const row of logs) {
      const tid = row?.metadata && typeof row.metadata === 'object' ? row.metadata.trace_id : null;
      if (tid == null || tid === '') {
        noTrace.push(row);
        continue;
      }
      const key = String(tid);
      const cur = byTrace.get(key);
      if (!cur || row.id > cur.id) byTrace.set(key, row);
    }
    const merged = [...byTrace.values(), ...noTrace];
    merged.sort((a, b) => b.id - a.id);
    return merged;
  }, [logs]);

  useEffect(() => {
    if (selectedId == null) return;
    if (displayLogs.some((r) => r.id === selectedId)) return;
    const row = logs.find((r) => r.id === selectedId);
    const tid = row?.metadata?.trace_id;
    if (tid == null || tid === '') return;
    const next = displayLogs.find((r) => r.metadata?.trace_id === tid);
    if (next) setSelectedId(next.id);
  }, [selectedId, logs, displayLogs]);

  useEffect(() => {
    if (!detailModalOpen || selectedId == null) return;
    const still =
      displayLogs.some((r) => r.id === selectedId) || logs.some((r) => r.id === selectedId);
    if (!still) {
      setDetailModalOpen(false);
      setSelectedId(null);
    }
  }, [detailModalOpen, selectedId, displayLogs, logs]);

  const selectedLog = useMemo(
    () => displayLogs.find((l) => l.id === selectedId) || logs.find((l) => l.id === selectedId) || null,
    [displayLogs, logs, selectedId],
  );

  const groupedLogs = useMemo(() => {
    const groups = [];
    let currentGroup = null;

    for (const row of displayLogs) {
      const meta = readMetadata(row);
      const date = new Date(row.timestamp);
      const dateStr = date.toLocaleDateString(undefined, {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      });

      if (!currentGroup || currentGroup.dateStr !== dateStr) {
        currentGroup = { dateStr, rows: [] };
        groups.push(currentGroup);
      }
      currentGroup.rows.push({ ...row, meta });
    }
    return groups;
  }, [displayLogs]);

  const clearDb = async () => {
    const msg = 'Delete all persisted RAG Fusion Proxy journal entries from the database?';
    if (!window.confirm(msg)) return;
    try {
      await clearProxyJournal();
      setSelectedId(null);
      setDetailModalOpen(false);
      await loadJournal();
    } catch (e) {
      setErr(String(e.message || e));
    }
  };

  const openEntry = (id) => {
    setSelectedId(id);
    setDetailModalOpen(true);
  };

  const journalHeadingId = 'rag-fusion-journal-heading';
  const blurb = (
    <>
      Persisted proxy requests (SQLite, <code>session_id=proxy</code>). The list refreshes every few seconds while this
      tab is open. Use the <strong>Traces</strong> subtab for the in-memory buffer. Click a row to open full detail.
    </>
  );

  return (
    <div className="dashboard-layout">
      <section className="app-default-card" aria-labelledby={journalHeadingId}>
        <div className="dashboard-card-header">
          <h2 id={journalHeadingId}>Journal</h2>
          <div className="dashboard-card-actions">
            <CoreUIButton variant="primary" onClick={() => loadJournal()} disabled={loading}>
              Refresh
            </CoreUIButton>
            <CoreUIButton variant="primary" onClick={clearDb}>
              Clear DB history
            </CoreUIButton>
          </div>
        </div>
        <p className="dashboard-card-muted">{blurb}</p>
        {err && <div className="dashboard-card-error">{err}</div>}

        <div className="proxy-journal-toolbar">
          <label className="dashboard-card-muted">
            Period{' '}
            <select
              className="dashboard-card-field"
              value={period}
              onChange={(e) => {
                setPeriod(e.target.value);
                setSelectedDate(null);
              }}
              aria-label="Journal period"
            >
              <option value="day">Today</option>
              <option value="week">Last 7 days</option>
              <option value="month">This month</option>
              <option value="year">This year</option>
              <option value="all">All time</option>
            </select>
          </label>
          {period === 'all' ? null : (
            <label className="dashboard-card-muted">
              Day{' '}
              <input
                type="date"
                className="dashboard-card-field"
                onChange={(e) => {
                  const v = e.target.value;
                  if (!v) setSelectedDate(null);
                  else setSelectedDate(new Date(v + 'T12:00:00'));
                }}
                aria-label="Pick calendar day"
              />
            </label>
          )}
        </div>

        {loading && <p className="dashboard-card-muted">Loading…</p>}
        {!loading && logs.length === 0 && <p className="dashboard-card-muted">No journal entries.</p>}
        {!loading && groupedLogs.length > 0 && (
          <div className="proxy-journal-groups" aria-busy={loading}>
            {groupedLogs.map((group) => (
              <div key={group.dateStr} className="proxy-journal-group">
                <h3 className="proxy-journal-group-title">{group.dateStr}</h3>
                <ul className="proxy-journal-list">
                  {group.rows.map((row) => (
                    <li key={row.id}>
                      <button
                        type="button"
                        onClick={() => openEntry(row.id)}
                        className={`proxy-journal-list-item${
                          detailModalOpen && selectedId === row.id ? ' proxy-journal-list-item--active' : ''
                        }`}
                      >
                        <div className="proxy-journal-list-item-header">
                          <span className="proxy-journal-list-item-msg">{formatLogMessage(row.message, row.meta)}</span>
                          {hasImage(row.meta) && (
                            <span className="material-symbols-outlined proxy-journal-list-item-image-icon">
                              image
                            </span>
                          )}
                        </div>
                        <span className="proxy-journal-list-item-time">
                          {new Date(row.timestamp).toLocaleTimeString(undefined, {
                            hour: '2-digit',
                            minute: '2-digit',
                            second: '2-digit',
                          })}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>
        )}
      </section>

      <ProxyTraceDetailModal
        log={selectedLog}
        isOpen={Boolean(detailModalOpen && selectedLog)}
        onClose={() => setDetailModalOpen(false)}
      />
    </div>
  );
}
