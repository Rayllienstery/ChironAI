import React, { useCallback, useEffect, useState } from 'react';
import {
  getClawCodeStatus,
  getClawCodeTraces,
  clearClawCodeTraces,
} from '../services/api';
import '../styles/components/DashboardTab.css';
import { summarizeClawTraceMeta } from '../utils/clawTraceSummary';
import ClawTraceSummaryCards from './ClawTraceSummaryCards';

const LIVE_POLL_MS = 3000;

export default function ClawProxyTracesTab() {
  const [status, setStatus] = useState(null);
  const [traces, setTraces] = useState([]);
  const [liveTraces, setLiveTraces] = useState([]);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(false);

  const loadDetailTraces = useCallback(async () => {
    setErr(null);
    try {
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
  }, []);

  useEffect(() => {
    loadDetailTraces();
  }, [loadDetailTraces]);

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

  const doClearTraces = async () => {
    setBusy(true);
    setErr(null);
    try {
      await clearClawCodeTraces();
      await loadDetailTraces();
      const data = await getClawCodeTraces(25);
      setLiveTraces(data.traces || []);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setBusy(false);
    }
  };

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
        <section className="app-default-card" aria-labelledby="claw-traces-unavailable-heading">
          <div className="dashboard-card-header">
            <h2 id="claw-traces-unavailable-heading">Traces</h2>
          </div>
          <p className="dashboard-card-muted">
            ClawCode is not available ({status.reason || 'unknown'}). Install <code>CoreModules/ClawCode</code> and
            restart the app.
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="dashboard-layout">
      <section className="app-default-card" aria-labelledby="claw-traces-heading">
        <div className="dashboard-card-header">
          <h2 id="claw-traces-heading">Traces</h2>
          <div className="dashboard-card-actions">
            <button type="button" className="dashboard-primary-btn" onClick={doClearTraces} disabled={busy}>
              Clear trace buffer
            </button>
            <button type="button" className="dashboard-primary-btn" onClick={loadDetailTraces} disabled={busy}>
              Refresh
            </button>
          </div>
        </div>
        <p className="dashboard-card-muted">
          Last agent runs: model, steps (model_call / rag_query), token estimates, RSS when psutil is installed.
        </p>
        {err && <div className="dashboard-card-error">{err}</div>}
        <div className="dashboard-card-scroll">
          {traces.length === 0 && <p className="dashboard-card-muted">No traces yet.</p>}
          {traces.map((t) => (
            <details key={t.trace_id} className="dashboard-trace-item">
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

      <section className="app-default-card" aria-labelledby="claw-traces-live-heading">
        <h3 id="claw-traces-live-heading" className="dashboard-card-header" style={{ margin: 0 }}>
          Live buffer (RAM)
        </h3>
        <p className="dashboard-card-muted" style={{ marginTop: 8 }}>
          In-memory runs only until process restart; polled every few seconds while this tab is open.
        </p>
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
    </div>
  );
}
