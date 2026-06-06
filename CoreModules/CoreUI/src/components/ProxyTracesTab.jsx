import { useCallback, useEffect, useMemo, useState } from 'react';
import { getLlmProxyStatus, getProxyTraces, clearProxyTraces } from '../services/api';
import '../styles/components/DashboardTab.css';
import CoreUIButton from './CoreUIButton';
import ProxyTraceDetailModal from './ProxyTraceDetailModal';
import { proxyTraceToolLimitWarning } from '../utils/proxyTraceWarnings';

const LIVE_POLL_MS = 3000;

function TraceToolLimitWarning({ trace, compact = false }) {
  const warning = proxyTraceToolLimitWarning(trace);
  if (!warning) return null;
  if (compact) {
    return <span className="coreui-status-pill coreui-status-pill--warning">Tool cap reached</span>;
  }
  return (
    <div className="coreui-panel-note coreui-panel-note--warning" role="alert">
      {warning}
    </div>
  );
}

function formatLogMessage(trace) {
  let text = trace.user_query || '';
  if (!text) return 'Trace ' + (trace.trace_id || '').slice(0, 8);
  return text.replace(/<environment_details>[\s\S]*?<\/environment_details>/g, '').trim();
}

function hasImage(trace) {
  if (trace.has_image) return true;
  const messages = trace.request?.messages;
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

function formatJournalTime(timestamp) {
  if (!timestamp) return '-';
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

/**
 * Tab for browsing recent LLM proxy traces and opening the detail modal
 * for any single request.
 */
export default function ProxyTracesTab() {
  const [status, setStatus] = useState(null);
  const [traces, setTraces] = useState([]);
  const [liveTraces, setLiveTraces] = useState([]);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [selectedTrace, setSelectedTrace] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);

  const loadDetailTraces = useCallback(async () => {
    setErr(null);
    try {
      const s = await getLlmProxyStatus();
      const available = Boolean(s.enabled);
      setStatus({
        available,
        reason: available ? '' : String(s.health || 'RAG Fusion Proxy is disabled in settings.'),
      });
      if (!available) {
        setTraces([]);
        return;
      }
      const t = await getProxyTraces(50);
      setTraces(t.traces || []);
    } catch (e) {
      setErr(String(e.message || e));
      setTraces([]);
    }
  }, []);

  useEffect(() => {
    loadDetailTraces();
  }, [loadDetailTraces]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const data = await getProxyTraces(25);
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

  const doClearTraces = async () => {
    const msg = 'Clear all in-memory traces?';
    if (!window.confirm(msg)) return;
    setBusy(true);
    setErr(null);
    try {
      await clearProxyTraces();
      await loadDetailTraces();
      const data = await getProxyTraces(25);
      setLiveTraces(data.traces || []);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const unavailableHeadingId = 'rag-fusion-traces-unavailable-heading';
  const mainHeadingId = 'rag-fusion-traces-heading';
  const liveHeadingId = 'rag-fusion-traces-live-heading';

  if (!status) {
    return (
      <div className="dashboard-layout">
        <p className="dashboard-card-muted">Loading…</p>
      </div>
    );
  }

  if (!status.available) {
    return (
      <div className="dashboard-layout">
        <section className="app-default-card" aria-labelledby={unavailableHeadingId}>
          <div className="dashboard-card-header">
            <h2 id={unavailableHeadingId}>Traces</h2>
          </div>
          <p className="dashboard-card-muted">
            RAG Fusion Proxy is not available ({status.reason || 'unknown'}). Enable the proxy in app settings and ensure
            the server is running.
          </p>
        </section>
      </div>
    );
  }

  const intro =
    'Recent proxy runs: resolved model, pipeline step timings (RAG sub-steps, provider chat), token estimates when present.';

  const selectedLog = useMemo(() => {
    if (!selectedTrace) return null;
    return {
      metadata: selectedTrace,
      timestamp: selectedTrace.timestamp || new Date().toISOString(),
    };
  }, [selectedTrace]);

  return (
    <div className="dashboard-layout">
      <section className="app-default-card" aria-labelledby={mainHeadingId}>
        <div className="dashboard-card-header">
          <h2 id={mainHeadingId}>Traces</h2>
          <div className="dashboard-card-actions">
            <CoreUIButton variant="primary" onClick={doClearTraces} disabled={busy}>
              Clear trace buffer
            </CoreUIButton>
            <CoreUIButton variant="primary" onClick={loadDetailTraces} disabled={busy}>
              Refresh
            </CoreUIButton>
          </div>
        </div>
        <p className="dashboard-card-muted">{intro}</p>
        {err && <div className="dashboard-card-error">{err}</div>}

        <div className="proxy-journal-groups" style={{ marginTop: 'var(--md-sys-spacing-md)' }}>
          <div className="proxy-journal-group">
            <ul className="proxy-journal-list">
              {traces.length === 0 && <li className="dashboard-card-muted coreui-p-md">No traces yet.</li>}
              {traces.map((t, i) => (
                <li key={`${t.trace_id || 'trace'}-d-${i}`}>
                  <button
                    type="button"
                    className={`proxy-journal-list-item${
                      modalOpen && selectedTrace?.trace_id === t.trace_id ? ' proxy-journal-list-item--active' : ''
                    }`}
                    onClick={() => {
                      setSelectedTrace(t);
                      setModalOpen(true);
                    }}
                  >
                    <div className="proxy-journal-list-item-header">
                      <span className="proxy-journal-list-item-msg">{formatLogMessage(t)}</span>
                      {hasImage(t) && (
                        <span className="material-symbols-outlined proxy-journal-list-item-image-icon">
                          image
                        </span>
                      )}
                    </div>
                    <div className="proxy-journal-list-item-meta-row">
                      <span className="proxy-journal-list-item-trace">
                        trace id: <code>{t.trace_id ? String(t.trace_id) : '-'}</code>
                      </span>
                      <span className="proxy-journal-list-item-time">{formatJournalTime(t.timestamp)}</span>
                    </div>
                    <div className="proxy-journal-list-item-stats">
                      <span>
                        Model: <code>{formatJournalValue(t.resolved_model || t.model)}</code>
                      </span>
                      <span>Latency: {formatJournalValue(t.elapsed_ms || t.latency_ms, ' ms')}</span>
                      <span>Steps: {formatJournalValue(t.step_count)}</span>
                      {t.error && <span className="dashboard-card-error">Error: {t.error}</span>}
                      <TraceToolLimitWarning trace={t} compact />
                    </div>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="app-default-card" aria-labelledby={liveHeadingId}>
        <h3 id={liveHeadingId} className="dashboard-card-header">
          Live buffer (RAM)
        </h3>
        <p className="dashboard-card-muted">
          In-memory runs only until process restart; polled every few seconds while this tab is open.
        </p>
        <div className="proxy-journal-groups" style={{ marginTop: 'var(--md-sys-spacing-md)' }}>
          <div className="proxy-journal-group">
            <ul className="proxy-journal-list">
              {liveTraces.length === 0 && <li className="dashboard-card-muted coreui-p-md">No in-memory traces.</li>}
              {liveTraces.map((t, i) => (
                <li key={`${t.trace_id || 'trace'}-l-${i}`}>
                  <div className="proxy-journal-list-item">
                    <div className="proxy-journal-list-item-header">
                      <span className="proxy-journal-list-item-msg">{formatLogMessage(t)}</span>
                    </div>
                    <div className="proxy-journal-list-item-meta-row">
                      <span className="proxy-journal-list-item-trace">
                        trace id: <code>{t.trace_id ? String(t.trace_id) : '-'}</code>
                      </span>
                      <span className="proxy-journal-list-item-time">{formatJournalTime(t.timestamp)}</span>
                    </div>
                    <div className="proxy-journal-list-item-stats">
                      <span>
                        Model: <code>{formatJournalValue(t.resolved_model || t.model)}</code>
                      </span>
                      <span>Latency: {formatJournalValue(t.elapsed_ms || t.latency_ms, ' ms')}</span>
                      <TraceToolLimitWarning trace={t} compact />
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <ProxyTraceDetailModal
        log={selectedLog}
        isOpen={Boolean(modalOpen && selectedLog)}
        onClose={() => setModalOpen(false)}
      />
    </div>
  );
}
