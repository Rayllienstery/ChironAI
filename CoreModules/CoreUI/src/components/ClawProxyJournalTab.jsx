import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  getClawCodeJournal,
  clearClawCodeJournal,
  getClawCodeTraces,
  clearClawCodeTraces,
} from '../services/api';
import '../styles/components/DashboardTab.css';
import { summarizeClawTraceMeta } from '../utils/clawTraceSummary';
import ClawTraceSummaryCards from './ClawTraceSummaryCards';

const JOURNAL_LIMIT = 2000;
const LIVE_POLL_MS = 3000;

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

function StepBlock({ step, index }) {
  if (!step || typeof step !== 'object') return null;
  const kind = step.kind || 'unknown';
  return (
    <details className="dashboard-trace-item" style={{ marginBottom: 8 }}>
      <summary>
        Step {index + 1}: <code>{kind}</code>
        {step.step != null ? ` (agent step ${step.step})` : ''}
        {step.ok === false ? ' · failed' : ''}
      </summary>
      <div className="dashboard-card-muted" style={{ marginTop: 8 }}>
        {kind === 'model_call' && (
          <>
            {step.model != null && (
              <p>
                <strong>Model:</strong> <code>{step.model}</code>
              </p>
            )}
            {(step.prompt_tokens_est != null || step.completion_tokens_est != null) && (
              <p className="dashboard-card-muted" style={{ fontSize: 12 }}>
                Token est.: prompt {step.prompt_tokens_est ?? '—'} · completion {step.completion_tokens_est ?? '—'}
              </p>
            )}
            {step.finish_reason != null && (
              <p>
                <strong>Finish:</strong> <code>{step.finish_reason}</code>
              </p>
            )}
            {step.thinking_raw != null && String(step.thinking_raw).trim() !== '' && (
              <div style={{ marginTop: 8 }}>
                <strong>Thinking (raw)</strong>
                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 280, overflow: 'auto', fontSize: 12 }}>
                  {step.thinking_raw}
                </pre>
              </div>
            )}
            {step.assistant_content_raw != null && String(step.assistant_content_raw).trim() !== '' && (
              <div style={{ marginTop: 8 }}>
                <strong>Assistant content (raw)</strong>
                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                  {step.assistant_content_raw}
                </pre>
              </div>
            )}
            {step.assistant_visible != null && String(step.assistant_visible).trim() !== '' && (
              <div style={{ marginTop: 8 }}>
                <strong>Assistant (merged visible)</strong>
                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                  {step.assistant_visible}
                </pre>
              </div>
            )}
            {Array.isArray(step.tool_calls) && step.tool_calls.length > 0 && (
              <div style={{ marginTop: 8 }}>
                <strong>Tool calls</strong>
                <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                  {JSON.stringify(step.tool_calls, null, 2)}
                </pre>
              </div>
            )}
            {step.error != null && (
              <p className="dashboard-card-error">{String(step.error)}</p>
            )}
          </>
        )}
        {kind === 'tool_rag' && (
          <>
            <p>
              <strong>Query:</strong> {step.query || '—'}
            </p>
            <p>
              Chunks: {step.chunks ?? '—'} · max_score: {step.max_score ?? '—'} · context_chars:{' '}
              {step.context_chars ?? '—'}
            </p>
            {step.error != null && <p className="dashboard-card-error">{String(step.error)}</p>}
            {Array.isArray(step.chunks_info) && step.chunks_info.length > 0 && (
              <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 240, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(step.chunks_info, null, 2)}
              </pre>
            )}
          </>
        )}
        {kind === 'tool_skill' && (
          <>
            <p>
              <strong>Invocation:</strong> {step.invocation || '—'}
            </p>
            {step.skill_id != null && String(step.skill_id).trim() !== '' && (
              <p>
                <strong>skill_id:</strong> <code>{step.skill_id}</code>
              </p>
            )}
            <p>
              context_chars: {step.context_chars ?? '—'} · duration_ms: {step.duration_ms ?? '—'}
            </p>
            {step.error != null && <p className="dashboard-card-error">{String(step.error)}</p>}
          </>
        )}
        {kind === 'tool_pass_through' && (
          <>
            <p>
              <strong>Tools returned to IDE:</strong>{' '}
              {Array.isArray(step.names) && step.names.length > 0 ? step.names.join(', ') : '—'}
            </p>
            <details className="dashboard-trace-item" style={{ marginTop: 8 }}>
              <summary>Raw step JSON</summary>
              <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{JSON.stringify(step, null, 2)}</pre>
            </details>
          </>
        )}
        {(kind === 'tool_unhandled' || kind === 'config_error') && (
          <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>
            {JSON.stringify(step, null, 2)}
          </pre>
        )}
        {kind !== 'model_call' &&
          kind !== 'tool_rag' &&
          kind !== 'tool_skill' &&
          kind !== 'tool_pass_through' &&
          kind !== 'tool_unhandled' &&
          kind !== 'config_error' && (
            <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>
              {JSON.stringify(step, null, 2)}
            </pre>
          )}
      </div>
    </details>
  );
}

export default function ClawProxyJournalTab() {
  const [period, setPeriod] = useState('week');
  const [selectedDate, setSelectedDate] = useState(null);
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [selectedId, setSelectedId] = useState(null);
  const [showRaw, setShowRaw] = useState(false);
  const [liveTraces, setLiveTraces] = useState([]);

  const loadJournal = useCallback(async (opts = {}) => {
    const silent = opts.silent === true;
    if (!silent) {
      setLoading(true);
      setErr(null);
    }
    try {
      const { from, to } = getDateRangeForJournal(period, selectedDate);
      const data = await getClawCodeJournal({
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
  }, [period, selectedDate]);

  useEffect(() => {
    loadJournal();
  }, [loadJournal]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await getClawCodeTraces(25);
        if (!cancelled) setLiveTraces(data.traces || []);
      } catch {
        if (!cancelled) setLiveTraces([]);
      }
    };
    poll();
    const t = setInterval(poll, LIVE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const poll = () => {
      if (cancelled || document.visibilityState !== 'visible') return;
      loadJournal({ silent: true });
    };
    poll();
    const t = setInterval(poll, LIVE_POLL_MS);
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

  const selectedLog = useMemo(
    () => displayLogs.find((l) => l.id === selectedId) || logs.find((l) => l.id === selectedId) || null,
    [displayLogs, logs, selectedId],
  );
  const meta = selectedLog?.metadata && typeof selectedLog.metadata === 'object' ? selectedLog.metadata : null;
  const traceSummary = useMemo(() => summarizeClawTraceMeta(meta), [meta]);

  const clearDb = async () => {
    if (!window.confirm('Delete all persisted ClawCode journal entries from the database?')) return;
    try {
      await clearClawCodeJournal();
      setSelectedId(null);
      await loadJournal();
    } catch (e) {
      setErr(String(e.message || e));
    }
  };

  const clearRam = async () => {
    try {
      await clearClawCodeTraces();
      const data = await getClawCodeTraces(25);
      setLiveTraces(data.traces || []);
    } catch (e) {
      setErr(String(e.message || e));
    }
  };

  return (
    <div className="dashboard-layout">
      <section className="app-default-card" aria-labelledby="claw-journal-heading">
        <div className="dashboard-card-header">
          <h2 id="claw-journal-heading">Journal</h2>
          <div className="dashboard-card-actions">
            <button type="button" className="dashboard-primary-btn" onClick={() => loadJournal()} disabled={loading}>
              Refresh
            </button>
            <button type="button" className="dashboard-primary-btn" onClick={clearRam}>
              Clear live buffer
            </button>
            <button type="button" className="dashboard-primary-btn" onClick={clearDb}>
              Clear DB history
            </button>
          </div>
        </div>
        <p className="dashboard-card-muted">
          Persisted agent traces (one row per run, updated as the agent progresses). The list refreshes every few seconds
          while this tab is open. Live buffer shows the last in-memory runs only until restart.
        </p>
        {err && <div className="dashboard-card-error">{err}</div>}
      </section>

      <section className="app-default-card" aria-labelledby="claw-journal-live-heading">
        <h3 id="claw-journal-live-heading" className="dashboard-card-header" style={{ margin: 0 }}>
          Live buffer (RAM)
        </h3>
        <div className="dashboard-card-scroll" style={{ maxHeight: 200 }}>
          {liveTraces.length === 0 && <p className="dashboard-card-muted">No in-memory traces.</p>}
          {liveTraces.map((t) => (
            <div key={t.trace_id} className="dashboard-kv-row">
              <code>{(t.trace_id || '').slice(0, 8)}</code>
              <span className="dashboard-card-muted">
                {t.elapsed_ms}ms · {t.step_count} steps · {t.resolved_model}
                {t.error ? ` · ${t.error}` : ''}
              </span>
            </div>
          ))}
        </div>
      </section>

      <div className="dashboard-claw-two-col" style={{ alignItems: 'flex-start' }}>
        <div className="dashboard-claw-col">
          <section className="app-default-card">
            <div className="dashboard-card-actions" style={{ flexWrap: 'wrap', marginBottom: 12 }}>
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
            <div className="dashboard-card-scroll" style={{ maxHeight: 420 }}>
              {loading && <p className="dashboard-card-muted">Loading…</p>}
              {!loading && logs.length === 0 && <p className="dashboard-card-muted">No journal entries.</p>}
              {!loading &&
                displayLogs.map((row) => (
                  <button
                    key={row.id}
                    type="button"
                    onClick={() => setSelectedId(row.id)}
                    className="claw-journal-row"
                    style={{
                      display: 'block',
                      width: '100%',
                      textAlign: 'left',
                      cursor: 'pointer',
                      border: row.id === selectedId ? '2px solid var(--accent, #6366f1)' : undefined,
                      borderRadius: 6,
                      marginBottom: 6,
                      padding: '8px 10px',
                      background: 'var(--card-bg, transparent)',
                    }}
                  >
                    <span style={{ opacity: 0.85, fontSize: 12 }}>{row.timestamp}</span>
                    <span style={{ display: 'block', marginTop: 4 }}>{row.message}</span>
                  </button>
                ))}
            </div>
          </section>
        </div>

        <div className="dashboard-claw-col">
          <section className="app-default-card">
            <div className="dashboard-card-header">
              <h3 style={{ margin: 0 }}>Detail</h3>
              <label className="dashboard-card-muted" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" checked={showRaw} onChange={(e) => setShowRaw(e.target.checked)} />
                Raw JSON
              </label>
            </div>
            {!selectedLog && <p className="dashboard-card-muted">Select an entry from the list.</p>}
            {selectedLog && showRaw && (
              <pre style={{ whiteSpace: 'pre-wrap', maxHeight: 560, overflow: 'auto', fontSize: 12 }}>
                {JSON.stringify(meta || selectedLog, null, 2)}
              </pre>
            )}
            {selectedLog && !showRaw && meta && (
              <div className="dashboard-card-scroll" style={{ maxHeight: 560 }}>
                <ClawTraceSummaryCards summary={traceSummary} />
                {meta.request != null && (
                  <details className="dashboard-trace-item">
                    <summary>
                      Request snapshot
                      {Array.isArray(meta.request.messages) ? ` · ${meta.request.messages.length} messages` : ''}
                      {' · '}
                      {Array.isArray(meta.request.client_tool_names)
                        ? `${meta.request.client_tool_names.length} client tools`
                        : '0 client tools'}
                      {meta.request.merge_client_tools != null
                        ? ` · merge_client_tools: ${meta.request.merge_client_tools ? 'yes' : 'no'}`
                        : ''}
                    </summary>
                    <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>
                      {JSON.stringify(meta.request, null, 2)}
                    </pre>
                  </details>
                )}
                {Array.isArray(meta.steps) && meta.steps.length > 0 && (
                  <div style={{ marginTop: 12 }}>
                    <strong>Steps</strong>
                    {meta.steps.map((s, i) => (
                      <StepBlock key={i} step={s} index={i} />
                    ))}
                  </div>
                )}
                {meta.final_message != null && (
                  <div style={{ marginTop: 16 }}>
                    <strong>Final answer</strong>
                    <pre style={{ whiteSpace: 'pre-wrap', marginTop: 8, fontSize: 12 }}>
                      {meta.final_message.content != null && meta.final_message.content !== ''
                        ? meta.final_message.content
                        : '(no text content)'}
                    </pre>
                    {meta.final_message.finish_reason != null && (
                      <p className="dashboard-card-muted">finish_reason: {meta.final_message.finish_reason}</p>
                    )}
                  </div>
                )}
              </div>
            )}
            {selectedLog && !showRaw && !meta && (
              <p className="dashboard-card-muted">No metadata on this row (legacy or empty).</p>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
