import { useState, useEffect, useCallback, useMemo } from 'react';
import { getProxyJournal, clearProxyJournal } from '../services/api';
import '../styles/components/DashboardTab.css';
import CoreUIButton from './CoreUIButton';
import ProxyTraceDetailModal from './ProxyTraceDetailModal';

const PAGE_SIZE = 50;
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
    text = msg.replace(/^Proxy request\s*(\([^)]+\))?:\s*/, '');
  }
  if (!text) return '';

  return text.replace(/<environment_details>[\s\S]*?<\/environment_details>/g, '').trim();
}

function formatJournalTime(timestamp) {
  return new Date(timestamp).toLocaleTimeString(undefined, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hourCycle: 'h23',
  });
}

function formatJournalValue(value, suffix = '') {
  if (value == null || value === '') return '-';
  return `${value}${suffix}`;
}

function getAgentStepCount(meta) {
  const count = Number(meta?.agent_step_count);
  return Number.isFinite(count) && count > 0 ? count : 1;
}

/**
 * Journal tab for browsing per-day proxy request logs.
 * Supports day/week/month filters and opens a detail modal for any log entry.
 */
export default function ProxyJournalTab() {
  const [period, setPeriod] = useState('week');
  const [selectedDate, setSelectedDate] = useState(null);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [detailModalOpen, setDetailModalOpen] = useState(false);

  const dateRange = useMemo(
    () => getDateRangeForJournal(period, selectedDate),
    [period, selectedDate],
  );

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE) || 1);
  const pageStart = total === 0 ? 0 : (page - 1) * PAGE_SIZE + 1;
  const pageEnd = total === 0 ? 0 : Math.min(page * PAGE_SIZE, total);

  const loadPage = useCallback(
    async (targetPage, opts = {}) => {
      const silent = opts.silent === true;
      if (!silent) {
        setLoading(true);
        setErr(null);
      }
      try {
        const { from, to } = dateRange;
        const data = await getProxyJournal({
          limit: PAGE_SIZE,
          offset: (targetPage - 1) * PAGE_SIZE,
          from: from || undefined,
          to: to || undefined,
        });
        setRows(data.logs || []);
        setTotal(typeof data.total === 'number' ? data.total : (data.logs || []).length);
        setPage(targetPage);
      } catch (e) {
        if (!silent) {
          setErr(String(e.message || e));
          setRows([]);
          setTotal(0);
        }
      } finally {
        if (!silent) setLoading(false);
      }
    },
    [dateRange],
  );

  const pollPageOne = useCallback(async () => {
    if (page !== 1) return;
    await loadPage(1, { silent: true });
  }, [page, loadPage]);

  useEffect(() => {
    void loadPage(1);
  }, [loadPage]);

  useEffect(() => {
    if (page !== 1) return undefined;
    let cancelled = false;
    const poll = () => {
      if (cancelled || document.visibilityState !== 'visible') return;
      void pollPageOne();
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
  }, [page, pollPageOne]);

  useEffect(() => {
    if (selectedId == null) return;
    if (rows.some((r) => r.id === selectedId)) return;
    setDetailModalOpen(false);
    setSelectedId(null);
  }, [selectedId, rows]);

  const selectedLog = useMemo(
    () => rows.find((l) => l.id === selectedId) || null,
    [rows, selectedId],
  );

  const groupedLogs = useMemo(() => {
    const groups = [];
    let currentGroup = null;

    for (const row of rows) {
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
  }, [rows]);

  const clearDb = async () => {
    const msg = 'Delete all persisted RAG Fusion Proxy journal entries from the database?';
    if (!window.confirm(msg)) return;
    try {
      await clearProxyJournal();
      setSelectedId(null);
      setDetailModalOpen(false);
      await loadPage(1);
    } catch (e) {
      setErr(String(e.message || e));
    }
  };

  const openEntry = (id) => {
    setSelectedId(id);
    setDetailModalOpen(true);
  };

  const goToPage = (nextPage) => {
    const clamped = Math.min(Math.max(1, nextPage), totalPages);
    if (clamped === page) return;
    void loadPage(clamped);
  };

  const journalHeadingId = 'rag-fusion-journal-heading';
  const blurb = (
    <>
      Persisted proxy requests (SQLite, <code>session_id=proxy</code>), grouped by agent task (
      <code>trace_chain_id</code>). Page 1 refreshes every few seconds while this tab is open. Use the{' '}
      <strong>Traces</strong> subtab for the in-memory buffer. Click a row to open the latest step detail.
    </>
  );

  return (
    <div className="dashboard-layout">
      <section className="app-default-card" aria-labelledby={journalHeadingId}>
        <div className="dashboard-card-header">
          <h2 id={journalHeadingId}>RAG Fusion Journal</h2>
          <div className="dashboard-card-actions">
            {loading && (
              <div className="status-text-updating" style={{ marginRight: '12px' }}>
                <span className="status-spinner" />
                <span style={{ fontSize: 'var(--md-sys-typescale-label-medium-size)' }}>Fetching data...</span>
              </div>
            )}
            <CoreUIButton variant="primary" onClick={() => loadPage(page)} disabled={loading}>
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
              aria-label="RAG Fusion Journal period"
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
        {!loading && rows.length === 0 && <p className="dashboard-card-muted">No journal entries.</p>}
        {!loading && groupedLogs.length > 0 && (
          <>
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
                          <div className="proxy-journal-list-item-meta-row">
                            <span className="proxy-journal-list-item-trace">
                              trace id: <code>{row.meta?.trace_id ? String(row.meta.trace_id) : '-'}</code>
                              {getAgentStepCount(row.meta) > 1 && (
                                <span className="proxy-journal-list-item-step-count">
                                  {getAgentStepCount(row.meta)} agent steps
                                </span>
                              )}
                            </span>
                            <span className="proxy-journal-list-item-time">{formatJournalTime(row.timestamp)}</span>
                          </div>
                          <div className="proxy-journal-list-item-stats" aria-label="Proxy request stats">
                            <span>
                              Model: <code>{formatJournalValue(row.meta?.model)}</code>
                            </span>
                            <span>Latency: {formatJournalValue(row.meta?.latency_ms, ' ms')}</span>
                            <span>Prompt tok.: {formatJournalValue(row.meta?.prompt_tokens)}</span>
                            <span>Completion tok.: {formatJournalValue(row.meta?.completion_tokens)}</span>
                            <span>Total tok.: {formatJournalValue(row.meta?.total_tokens)}</span>
                          </div>
                        </button>
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
            <div className="proxy-journal-pagination" aria-label="Journal pagination">
              <CoreUIButton variant="primary" onClick={() => goToPage(page - 1)} disabled={loading || page <= 1}>
                Previous
              </CoreUIButton>
              <span className="proxy-journal-pagination-summary">
                Page {page} of {totalPages}
                {total > 0 ? ` · ${pageStart}–${pageEnd} of ${total}` : ''}
              </span>
              <CoreUIButton
                variant="primary"
                onClick={() => goToPage(page + 1)}
                disabled={loading || page >= totalPages}
              >
                Next
              </CoreUIButton>
            </div>
          </>
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
