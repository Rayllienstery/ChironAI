import React, { useEffect, useMemo, useRef, useState } from 'react';
import { getClawCodeTraces, getProxyTraceCurrent } from '../services/api';
import { traceModelFields } from './ProxyTraceTab';
import { useNotificationCenter } from './NotificationCenterContext';

const POLL_MS = 1000;
const WIND_DOWN_MS = 10_000;

const LLM_LIVE_ID = 'llm-proxy-live';
const CLAW_LIVE_ID = 'claw-proxy-live';

const RING_R = 20;
const RING_C = 2 * Math.PI * RING_R;

function pickLastStepName(steps) {
  if (!Array.isArray(steps) || steps.length === 0) return null;
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const s = steps[i];
    if (s && s.duration_ms == null) {
      const n = s.name;
      return n != null && n !== '' ? String(n) : null;
    }
  }
  const last = steps[steps.length - 1];
  const n = last?.name;
  return n != null && n !== '' ? String(n) : null;
}

function WindDownRing({ endsAt }) {
  const [, setRafTick] = useState(0);
  const endsRef = useRef(endsAt);
  endsRef.current = endsAt;

  useEffect(() => {
    let cancelled = false;
    const loop = () => {
      if (cancelled) return;
      setRafTick((x) => x + 1);
      if (endsRef.current > Date.now()) {
        requestAnimationFrame(loop);
      }
    };
    requestAnimationFrame(loop);
    return () => {
      cancelled = true;
    };
  }, [endsAt]);

  const remaining = Math.max(0, endsAt - Date.now());
  if (remaining <= 0) return null;
  const frac = Math.min(1, remaining / WIND_DOWN_MS);
  const offset = RING_C * (1 - frac);
  const digit = Math.min(
    Math.ceil(WIND_DOWN_MS / 1000),
    Math.max(1, Math.ceil(remaining / 1000)),
  );

  return (
    <div className="notification-proxy-winddown">
      <svg
        className="notification-proxy-winddown-ring"
        width="48"
        height="48"
        viewBox="0 0 48 48"
        aria-hidden="true"
      >
        <circle className="notification-proxy-winddown-ring-track" cx="24" cy="24" r={RING_R} />
        <circle
          className="notification-proxy-winddown-ring-progress"
          cx="24"
          cy="24"
          r={RING_R}
          strokeDasharray={RING_C}
          strokeDashoffset={offset}
        />
        <text
          x="24"
          y="24"
          textAnchor="middle"
          dominantBaseline="central"
          className="notification-proxy-winddown-digit"
        >
          {digit}
        </text>
      </svg>
      <span className="notification-proxy-winddown-hint">Saving to history…</span>
    </div>
  );
}

/**
 * Polls LLM proxy trace + Claw live buffer; live card while busy, 10s wind-down then persist to History.
 */
export default function ProxiesLiveNotificationBridge({
  onOpenLlmProxyTrace,
  onOpenClawJournal,
  onOpenClawTraces,
}) {
  const {
    setLiveActivity,
    clearLiveActivity,
    persistNotification,
    sessionId,
    liveSuppressedIds,
    clearLiveSuppression,
  } = useNotificationCenter();

  const [proxyPayload, setProxyPayload] = useState(null);
  const [clawPayload, setClawPayload] = useState(null);
  const [llmWindDown, setLlmWindDown] = useState(null);
  const [clawWindDown, setClawWindDown] = useState(null);

  const prevLlmBusyRef = useRef(false);
  const sawClawInFlightRef = useRef(false);
  const lastFreshClawWindDownTidRef = useRef(null);
  const llmWindDownGenRef = useRef(0);
  const clawWindDownGenRef = useRef(0);

  const llmSuppressed = liveSuppressedIds.includes(LLM_LIVE_ID);
  const clawSuppressed = liveSuppressedIds.includes(CLAW_LIVE_ID);

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      try {
        const p = await getProxyTraceCurrent();
        if (!cancelled) setProxyPayload(p || null);
      } catch {
        /* keep previous */
      }
      try {
        const c = await getClawCodeTraces(8);
        if (!cancelled) setClawPayload(c || null);
      } catch {
        /* keep previous */
      }
    };

    tick();
    const id = setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  useEffect(() => {
    const p = proxyPayload;
    if (!p) return;

    const status = (p.status != null && p.status !== '' ? String(p.status) : 'Idle').trim();
    const busy = status !== 'Idle';
    const trace = p.trace;

    if (busy) {
      clearLiveSuppression(LLM_LIVE_ID);
      llmWindDownGenRef.current += 1;
      setLlmWindDown(null);
      prevLlmBusyRef.current = true;
      return;
    }

    if (prevLlmBusyRef.current && !busy && trace && !llmWindDown) {
      const model = traceModelFields(trace).headerShort;
      const stepLine = pickLastStepName(trace?.steps);
      const gen = ++llmWindDownGenRef.current;
      setLlmWindDown({
        gen,
        endsAt: Date.now() + WIND_DOWN_MS,
        status,
        model,
        stepLine,
        traceId: trace.trace_id != null ? String(trace.trace_id).slice(0, 12) : '',
      });
    }

    prevLlmBusyRef.current = busy;
  }, [proxyPayload, llmWindDown, clearLiveSuppression]);

  useEffect(() => {
    const c = clawPayload;
    if (!c || c.available === false) return;

    const traces = c.traces;
    const latest = Array.isArray(traces) && traces.length > 0 ? traces[0] : null;

    if (latest && latest.final === false) {
      clearLiveSuppression(CLAW_LIVE_ID);
      clawWindDownGenRef.current += 1;
      setClawWindDown(null);
      sawClawInFlightRef.current = true;
      return;
    }

    if (latest && latest.final === true) {
      const tid = latest.trace_id != null ? String(latest.trace_id) : '';
      const edgeWindDown = sawClawInFlightRef.current === true && !clawWindDown;
      const ts = Number(latest.ts_ms);
      const ageMs = Number.isFinite(ts) ? Date.now() - ts : Infinity;
      const freshFinalWindDown =
        tid &&
        !clawWindDown &&
        !edgeWindDown &&
        ageMs >= 0 &&
        ageMs < 12_000 &&
        lastFreshClawWindDownTidRef.current !== tid;

      if (edgeWindDown || freshFinalWindDown) {
        if (freshFinalWindDown) {
          lastFreshClawWindDownTidRef.current = tid;
        }
        const gen = ++clawWindDownGenRef.current;
        setClawWindDown({
          gen,
          endsAt: Date.now() + WIND_DOWN_MS,
          snap: {
            trace_id: latest.trace_id,
            step_count: latest.step_count,
            elapsed_ms: latest.elapsed_ms,
            resolved_model: latest.resolved_model,
            error: latest.error,
          },
        });
      }
      sawClawInFlightRef.current = false;
      return;
    }

    sawClawInFlightRef.current = false;
  }, [clawPayload, clawWindDown, clearLiveSuppression]);

  useEffect(() => {
    if (llmSuppressed) {
      llmWindDownGenRef.current += 1;
      setLlmWindDown(null);
    }
  }, [llmSuppressed]);

  useEffect(() => {
    if (clawSuppressed) {
      clawWindDownGenRef.current += 1;
      setClawWindDown(null);
    }
  }, [clawSuppressed]);

  useEffect(() => {
    if (!llmWindDown) return undefined;
    const { endsAt, status, model, stepLine, traceId, gen } = llmWindDown;
    const myEndsAt = endsAt;
    const delay = Math.max(0, endsAt - Date.now());
    const t = setTimeout(() => {
      void (async () => {
        try {
          if (!sessionId || gen !== llmWindDownGenRef.current) return;
          const parts = [model && `Model: ${model}`, status && `Last status: ${status}`].filter(Boolean);
          if (stepLine) parts.push(`Step: ${stepLine}`);
          if (traceId) parts.push(`Trace: ${traceId}`);
          await persistNotification({
            kind: 'event',
            source: 'llm-proxy',
            title: 'LLM Proxy finished',
            message: parts.join(' · ').slice(0, 800),
            metadata: { historyOnly: true },
          });
        } catch (e) {
          console.error('NotificationCenter: LLM wind-down persist failed', e);
        }
      })();
      setLlmWindDown((wd) => {
        if (wd && wd.endsAt === myEndsAt) {
          clearLiveActivity(LLM_LIVE_ID);
          return null;
        }
        return wd;
      });
    }, delay);
    return () => clearTimeout(t);
  }, [llmWindDown, sessionId, persistNotification, clearLiveActivity]);

  useEffect(() => {
    if (!clawWindDown) return undefined;
    const { endsAt, snap, gen } = clawWindDown;
    const myEndsAt = endsAt;
    const delay = Math.max(0, endsAt - Date.now());
    const t = setTimeout(() => {
      void (async () => {
        try {
          if (!sessionId || gen !== clawWindDownGenRef.current) return;
          const tid = snap.trace_id != null ? String(snap.trace_id).slice(0, 8) : '';
          const err = snap.error ? String(snap.error) : '';
          const msg = [
            tid && `Trace ${tid}`,
            snap.step_count != null && `${snap.step_count} steps`,
            snap.elapsed_ms != null && `${snap.elapsed_ms} ms`,
            snap.resolved_model && String(snap.resolved_model),
            err && `Error: ${err.slice(0, 200)}`,
          ]
            .filter(Boolean)
            .join(' · ');
          await persistNotification({
            kind: err ? 'error' : 'event',
            source: 'claw-proxy',
            title: err ? 'Claw Proxy finished with error' : 'Claw Proxy finished',
            message: msg.slice(0, 800),
            metadata: { historyOnly: true },
          });
        } catch (e) {
          console.error('NotificationCenter: Claw wind-down persist failed', e);
        }
      })();
      setClawWindDown((wd) => {
        if (wd && wd.endsAt === myEndsAt) {
          clearLiveActivity(CLAW_LIVE_ID);
          return null;
        }
        return wd;
      });
    }, delay);
    return () => clearTimeout(t);
  }, [clawWindDown, sessionId, persistNotification, clearLiveActivity]);

  const busyLlm = useMemo(() => {
    const p = proxyPayload;
    if (!p) return false;
    const status = (p.status != null && p.status !== '' ? String(p.status) : 'Idle').trim();
    return status !== 'Idle';
  }, [proxyPayload]);

  const clawInFlight = useMemo(() => {
    const c = clawPayload;
    if (!c || c.available === false) return false;
    const traces = c.traces;
    const latest = Array.isArray(traces) && traces.length > 0 ? traces[0] : null;
    return Boolean(latest && latest.final === false);
  }, [clawPayload]);

  const showLlm = !llmSuppressed && (busyLlm || llmWindDown != null);
  const showClaw = !clawSuppressed && (clawInFlight || clawWindDown != null);

  const llmNode = useMemo(() => {
    if (!showLlm) return null;

    if (llmWindDown != null && !busyLlm) {
      const { status, model, stepLine } = llmWindDown;
      return (
        <div className="proxy-live-notification notification-proxy-embed">
          <div className="proxy-live-notification-status">
            <span className="proxy-live-notification-label">Status</span>
            <span className="proxy-live-notification-value">{status}</span>
          </div>
          <div className="proxy-live-notification-row">
            <span className="proxy-live-notification-label">Model</span>
            <span className="proxy-live-notification-value proxy-live-notification-mono">{model}</span>
          </div>
          {stepLine ? (
            <div className="proxy-live-notification-row proxy-live-notification-step">
              <span className="proxy-live-notification-label">Step</span>
              <span className="proxy-live-notification-value">{stepLine}</span>
            </div>
          ) : null}
          <WindDownRing endsAt={llmWindDown.endsAt} />
          <div className="proxy-live-notification-actions">
            <button
              type="button"
              className="coreui-btn coreui-btn-small coreui-btn-ghost"
              onClick={onOpenLlmProxyTrace}
            >
              Proxy Trace
            </button>
          </div>
        </div>
      );
    }

    if (!proxyPayload) return null;

    const status = (
      proxyPayload.status != null && proxyPayload.status !== '' ? String(proxyPayload.status) : 'Idle'
    ).trim();
    const trace = proxyPayload.trace;
    const model = traceModelFields(trace).headerShort;
    const stepLine = pickLastStepName(trace?.steps);

    return (
      <div className="proxy-live-notification notification-proxy-embed">
        {busyLlm ? (
          <div className="proxy-live-notification-header">
            <span className="proxy-live-notification-pulse" aria-hidden="true" title="Active" />
          </div>
        ) : null}
        <div className="proxy-live-notification-status">
          <span className="proxy-live-notification-label">Status</span>
          <span className="proxy-live-notification-value">{status}</span>
        </div>
        <div className="proxy-live-notification-row">
          <span className="proxy-live-notification-label">Model</span>
          <span className="proxy-live-notification-value proxy-live-notification-mono">{model}</span>
        </div>
        {stepLine ? (
          <div className="proxy-live-notification-row proxy-live-notification-step">
            <span className="proxy-live-notification-label">Step</span>
            <span className="proxy-live-notification-value">{stepLine}</span>
          </div>
        ) : null}
        <div className="proxy-live-notification-actions">
          <button
            type="button"
            className="coreui-btn coreui-btn-small coreui-btn-ghost"
            onClick={onOpenLlmProxyTrace}
          >
            Proxy Trace
          </button>
        </div>
      </div>
    );
  }, [
    showLlm,
    proxyPayload,
    busyLlm,
    llmWindDown,
    onOpenLlmProxyTrace,
  ]);

  const clawNode = useMemo(() => {
    if (!showClaw) return null;

    if (clawWindDown != null && !clawInFlight) {
      const s = clawWindDown.snap;
      const tid = (s.trace_id && String(s.trace_id).slice(0, 8)) || '—';
      const steps = s.step_count;
      const model = s.resolved_model != null && s.resolved_model !== '' ? String(s.resolved_model) : '—';
      const err = s.error ? String(s.error) : '';

      return (
        <div className="claw-live-notification notification-proxy-embed">
          <div className="proxy-live-notification-row">
            <span className="proxy-live-notification-label">Trace</span>
            <span className="proxy-live-notification-value proxy-live-notification-mono">{tid}</span>
          </div>
          <div className="proxy-live-notification-row proxy-live-notification-row--inline">
            <span className="proxy-live-notification-label">Steps</span>
            <span className="proxy-live-notification-value">{steps != null ? String(steps) : '—'}</span>
            <span className="proxy-live-notification-sep" aria-hidden="true">
              ·
            </span>
            <span className="proxy-live-notification-label">ms</span>
            <span className="proxy-live-notification-value">
              {s.elapsed_ms != null ? String(s.elapsed_ms) : '—'}
            </span>
          </div>
          <div className="proxy-live-notification-row">
            <span className="proxy-live-notification-label">Model</span>
            <span className="proxy-live-notification-value proxy-live-notification-mono">{model}</span>
          </div>
          {err ? (
            <div className="proxy-live-notification-error" role="alert">
              {err.length > 200 ? `${err.slice(0, 200)}…` : err}
            </div>
          ) : null}
          <WindDownRing endsAt={clawWindDown.endsAt} />
          <div className="proxy-live-notification-actions">
            <button
              type="button"
              className="coreui-btn coreui-btn-small coreui-btn-ghost"
              onClick={onOpenClawTraces}
            >
              Traces
            </button>
            <button
              type="button"
              className="coreui-btn coreui-btn-small coreui-btn-ghost"
              onClick={onOpenClawJournal}
            >
              Journal
            </button>
          </div>
        </div>
      );
    }

    if (!clawPayload) return null;

    const traces = clawPayload.traces;
    const latest = Array.isArray(traces) && traces.length > 0 ? traces[0] : null;
    if (!latest) return null;

    const active = latest.final === false;
    const tid = (latest.trace_id && String(latest.trace_id).slice(0, 8)) || '—';
    const steps = latest.step_count;
    const model = latest.resolved_model != null && latest.resolved_model !== '' ? String(latest.resolved_model) : '—';
    const err = latest.error ? String(latest.error) : '';

    return (
      <div className="claw-live-notification notification-proxy-embed">
        {active ? (
          <div className="proxy-live-notification-header">
            <span className="proxy-live-notification-pulse" aria-hidden="true" title="Active" />
          </div>
        ) : null}
        <div className="proxy-live-notification-row">
          <span className="proxy-live-notification-label">Trace</span>
          <span className="proxy-live-notification-value proxy-live-notification-mono">{tid}</span>
        </div>
        <div className="proxy-live-notification-row proxy-live-notification-row--inline">
          <span className="proxy-live-notification-label">Steps</span>
          <span className="proxy-live-notification-value">{steps != null ? String(steps) : '—'}</span>
          <span className="proxy-live-notification-sep" aria-hidden="true">
            ·
          </span>
          <span className="proxy-live-notification-label">ms</span>
          <span className="proxy-live-notification-value">
            {latest.elapsed_ms != null ? String(latest.elapsed_ms) : '—'}
          </span>
        </div>
        <div className="proxy-live-notification-row">
          <span className="proxy-live-notification-label">Model</span>
          <span className="proxy-live-notification-value proxy-live-notification-mono">{model}</span>
        </div>
        {err ? (
          <div className="proxy-live-notification-error" role="alert">
            {err.length > 200 ? `${err.slice(0, 200)}…` : err}
          </div>
        ) : null}
        <div className="proxy-live-notification-actions">
          <button
            type="button"
            className="coreui-btn coreui-btn-small coreui-btn-ghost"
            onClick={onOpenClawTraces}
          >
            Traces
          </button>
          <button
            type="button"
            className="coreui-btn coreui-btn-small coreui-btn-ghost"
            onClick={onOpenClawJournal}
          >
            Journal
          </button>
        </div>
      </div>
    );
  }, [
    showClaw,
    clawPayload,
    clawInFlight,
    clawWindDown,
    onOpenClawJournal,
    onOpenClawTraces,
  ]);

  useEffect(() => {
    if (!llmNode || llmSuppressed) {
      clearLiveActivity(LLM_LIVE_ID);
      return () => clearLiveActivity(LLM_LIVE_ID);
    }
    setLiveActivity(LLM_LIVE_ID, 'llm-proxy', llmNode);
    return () => clearLiveActivity(LLM_LIVE_ID);
  }, [llmNode, llmSuppressed, setLiveActivity, clearLiveActivity]);

  useEffect(() => {
    if (!clawNode || clawSuppressed) {
      clearLiveActivity(CLAW_LIVE_ID);
      return () => clearLiveActivity(CLAW_LIVE_ID);
    }
    setLiveActivity(CLAW_LIVE_ID, 'claw-proxy', clawNode);
    return () => clearLiveActivity(CLAW_LIVE_ID);
  }, [clawNode, clawSuppressed, setLiveActivity, clearLiveActivity]);

  return null;
}
