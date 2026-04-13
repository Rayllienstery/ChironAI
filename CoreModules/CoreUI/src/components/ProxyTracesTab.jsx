import React, { useCallback, useEffect, useState } from 'react';
import {
  getClawCodeStatus,
  getClawCodeTraces,
  clearClawCodeTraces,
  getLlmProxyStatus,
  getProxyTraces,
  clearProxyTraces,
} from '../services/api';
import '../styles/components/DashboardTab.css';
import { summarizeClawTraceMeta } from '../utils/clawTraceSummary';
import ClawTraceSummaryCards from './ClawTraceSummaryCards';

const LIVE_POLL_MS = 3000;

/**
 * @param {{ variant?: 'claw' | 'ragFusion' }} props
 */
export default function ProxyTracesTab({ variant = 'claw' }) {
  const [status, setStatus] = useState(null);
  const [traces, setTraces] = useState([]);
  const [liveTraces, setLiveTraces] = useState([]);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const loadDetailTraces = useCallback(async () => {
    setErr(null);
    try {
      if (variant === 'ragFusion') {
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
        return;
      }
      const s = await getClawCodeStatus();
      setStatus(s);
      if (!s.available) {
        setTraces([]);
        return;
      }
      const t = await getClawCodeTraces(50);
      setTraces(t.traces || []);
    } catch (e) {
      setErr(String(e.message || e));
      setTraces([]);
    }
  }, [variant]);

  useEffect(() => {
    loadDetailTraces();
  }, [loadDetailTraces]);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        if (variant === 'ragFusion') {
          const data = await getProxyTraces(25);
          if (!cancelled) setLiveTraces(data.traces || []);
          return;
        }
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
  }, [variant]);

  const doClearTraces = async () => {
    setBusy(true);
    setErr(null);
    try {
      if (variant === 'ragFusion') {
        await clearProxyTraces();
      } else {
        await clearClawCodeTraces();
      }
      await loadDetailTraces();
      if (variant === 'ragFusion') {
        const data = await getProxyTraces(25);
        setLiveTraces(data.traces || []);
      } else {
        const data = await getClawCodeTraces(25);
        setLiveTraces(data.traces || []);
      }
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

  const unavailableHeadingId =
    variant === 'ragFusion' ? 'rag-fusion-traces-unavailable-heading' : 'claw-traces-unavailable-heading';
  const mainHeadingId = variant === 'ragFusion' ? 'rag-fusion-traces-heading' : 'claw-traces-heading';
  const liveHeadingId = variant === 'ragFusion' ? 'rag-fusion-traces-live-heading' : 'claw-traces-live-heading';

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
            {variant === 'ragFusion' ? (
              <>
                RAG Fusion Proxy is not available ({status.reason || 'unknown'}). Enable the proxy in app settings
                and ensure the server is running.
              </>
            ) : (
              <>
                ClawCode is not available ({status.reason || 'unknown'}). Install <code>CoreModules/ClawCode</code>{' '}
                and restart the app.
              </>
            )}
          </p>
        </section>
      </div>
    );
  }

  const intro =
    variant === 'ragFusion'
      ? 'Recent proxy runs: resolved model, pipeline step timings (RAG sub-steps, ollama_chat), token estimates when present.'
      : 'Last agent runs: model, steps (model_call / rag_query), token estimates, RSS when psutil is installed.';

  return (
    <div className="dashboard-layout">
      <section className="app-default-card" aria-labelledby={mainHeadingId}>
        <div className="dashboard-card-header">
          <h2 id={mainHeadingId}>Traces</h2>
          <div className="dashboard-card-actions">
            <button type="button" className="dashboard-primary-btn" onClick={doClearTraces} disabled={busy}>
              Clear trace buffer
            </button>
            <button type="button" className="dashboard-primary-btn" onClick={loadDetailTraces} disabled={busy}>
              Refresh
            </button>
          </div>
        </div>
        <p className="dashboard-card-muted">{intro}</p>
        {err && <div className="dashboard-card-error">{err}</div>}
        <div className="dashboard-card-scroll">
          {traces.length === 0 && <p className="dashboard-card-muted">No traces yet.</p>}
          {traces.map((t, i) => (
            <details key={`${t.trace_id || 'trace'}-d-${i}`} className="dashboard-trace-item">
              <summary>
                <code>{(t.trace_id || '').slice(0, 8)}</code> · {t.elapsed_ms}ms · {t.step_count} steps ·{' '}
                {t.resolved_model}
                {t.error ? ` · error: ${t.error}` : ''}
              </summary>
              <ClawTraceSummaryCards summary={summarizeClawTraceMeta(t)} />
              <details className="dashboard-trace-item" style={{ marginTop: 12 }}>
                <summary>Full JSON</summary>
                <pre style={{ whiteSpace: 'pre-wrap', fontSize: 12 }}>{JSON.stringify(t, null, 2)}</pre>
              </details>
            </details>
          ))}
        </div>
      </section>

      <section className="app-default-card" aria-labelledby={liveHeadingId}>
        <h3 id={liveHeadingId} className="dashboard-card-header" style={{ margin: 0 }}>
          Live buffer (RAM)
        </h3>
        <p className="dashboard-card-muted" style={{ marginTop: 8 }}>
          In-memory runs only until process restart; polled every few seconds while this tab is open.
        </p>
        <div className="dashboard-card-scroll" style={{ maxHeight: 200 }}>
          {liveTraces.length === 0 && <p className="dashboard-card-muted">No in-memory traces.</p>}
          {liveTraces.map((t, i) => (
            <div key={`${t.trace_id || 'trace'}-l-${i}`} className="dashboard-kv-row">
              <code>{(t.trace_id || '').slice(0, 8)}</code>
              <span className="dashboard-card-muted">
                {t.elapsed_ms}ms · {t.step_count} steps · {t.resolved_model}
                {t.error ? ` · ${t.error}` : ''}
              </span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
