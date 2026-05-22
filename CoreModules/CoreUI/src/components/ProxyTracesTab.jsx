import { useCallback, useEffect, useMemo, useState } from 'react';
import { getLlmProxyStatus, getProxyTraces, clearProxyTraces } from '../services/api';
import '../styles/components/DashboardTab.css';
import CoreUIButton from './CoreUIButton';
import CoreUIModal from './CoreUIModal';
import CoreUIPillTabs from './CoreUIPillTabs';
import { summarizeAgentTraceMeta } from '../utils/agentTraceSummary';
import { proxyTraceToolLimitWarning } from '../utils/proxyTraceWarnings';
import AgentTraceSummaryCards from './AgentTraceSummaryCards';

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

export default function ProxyTracesTab() {
  const [status, setStatus] = useState(null);
  const [traces, setTraces] = useState([]);
  const [liveTraces, setLiveTraces] = useState([]);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);
  const [selectedTrace, setSelectedTrace] = useState(null);
  const [modalOpen, setModalOpen] = useState(false);
  const [modalTab, setModalTab] = useState('formatted');

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
    'Recent proxy runs: resolved model, pipeline step timings (RAG sub-steps, ollama_chat), token estimates when present.';

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
        <div className="dashboard-card-scroll">
          {traces.length === 0 && <p className="dashboard-card-muted">No traces yet.</p>}
          {traces.map((t, i) => (
            <button
              key={`${t.trace_id || 'trace'}-d-${i}`}
              type="button"
              className="dashboard-trace-item dashboard-trace-item--clickable"
              onClick={() => {
                setSelectedTrace(t);
                setModalTab('formatted');
                setModalOpen(true);
              }}
            >
              <div className="dashboard-trace-item-header">
                <code>{(t.trace_id || '').slice(0, 8)}</code> · {t.elapsed_ms}ms · {t.step_count} steps ·{' '}
                {t.resolved_model}
                {t.error ? ` · error: ${t.error}` : ''}
              </div>
              <TraceToolLimitWarning trace={t} />
            </button>
          ))}
        </div>
      </section>

      <section className="app-default-card" aria-labelledby={liveHeadingId}>
        <h3 id={liveHeadingId} className="dashboard-card-header">
          Live buffer (RAM)
        </h3>
        <p className="dashboard-card-muted">
          In-memory runs only until process restart; polled every few seconds while this tab is open.
        </p>
        <div className="dashboard-card-scroll coreui-mono-block--compact">
          {liveTraces.length === 0 && <p className="dashboard-card-muted">No in-memory traces.</p>}
          {liveTraces.map((t, i) => (
            <div key={`${t.trace_id || 'trace'}-l-${i}`} className="dashboard-kv-row">
              <code>{(t.trace_id || '').slice(0, 8)}</code>
              <span className="dashboard-card-muted">
                {t.elapsed_ms}ms · {t.step_count} steps · {t.resolved_model}
                {t.error ? ` · ${t.error}` : ''}
              </span>
              <TraceToolLimitWarning trace={t} compact />
            </div>
          ))}
        </div>
      </section>

      {modalOpen && selectedTrace && (
        <CoreUIModal
          title={`Trace ${(selectedTrace.trace_id || '').slice(0, 8)}`}
          onClose={() => setModalOpen(false)}
        >
          <CoreUIPillTabs
            tabs={[
              { id: 'formatted', label: 'Formatted' },
              { id: 'full-json', label: 'Full Json' },
            ]}
            value={modalTab}
            onChange={setModalTab}
            ariaLabel="Trace view mode"
          />
          <div style={{ marginTop: 'var(--md-sys-spacing-md)' }}>
            {modalTab === 'formatted' && (
              <>
                <AgentTraceSummaryCards summary={summarizeAgentTraceMeta(selectedTrace)} />
                <TraceToolLimitWarning trace={selectedTrace} />
                <details className="dashboard-trace-item coreui-section-block" style={{ marginTop: 'var(--md-sys-spacing-md)' }}>
                  <summary>Full JSON</summary>
                  <pre className="coreui-mono-block">{JSON.stringify(selectedTrace, null, 2)}</pre>
                </details>
              </>
            )}
            {modalTab === 'full-json' && (
              <pre className="coreui-mono-block">{JSON.stringify(selectedTrace, null, 2)}</pre>
            )}
          </div>
        </CoreUIModal>
      )}
    </div>
  );
}
