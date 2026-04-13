import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getClawCodeTraces, getProxyTraceCurrent } from '../services/api';
import {
  clawTracePhaseKey,
  formatClawStepDuration,
  getClawTraceNotificationFields,
} from '../utils/clawLiveActivity';
import { getClawTraceUsageCapsules } from '../utils/clawTraceSummary';
import ClawCodeMarkIcon from './ClawCodeMarkIcon';
import { traceModelFields } from '../utils/proxyTraceModel';
import { useNotificationCenter } from './NotificationCenterContext';

const POLL_MS = 1000;
const WIND_DOWN_MS = 7_000;

const LEGACY_LLM_LIVE_ID = 'llm-proxy-live';
const LEGACY_CLAW_LIVE_ID = 'claw-proxy-live';

const CLAW_CODE_HEADER_ICON = <ClawCodeMarkIcon />;

/** One live card per trace id so multiple runs stack vertically. */
function proxyLiveSlotId(kind, traceId) {
  const raw = traceId != null && String(traceId).trim() !== '' ? String(traceId).trim() : 'unknown';
  const safe = raw.replace(/[^a-zA-Z0-9_-]+/g, '_').slice(0, 72);
  return kind === 'llm' ? `llm-proxy-live-${safe}` : `claw-proxy-live-${safe}`;
}

/**
 * @param {{ run_line?: string, step_primary?: string, step_secondary?: string, tone?: string }} fields
 * @param {{ showPulse?: boolean, stepElapsedMs?: number | null }} opts
 */
function ClawTraceTaskStepBlock({ fields, showPulse = false, stepElapsedMs = null }) {
  if (!fields) return null;
  const runLine = typeof fields.run_line === 'string' ? fields.run_line.trim() : '';
  const primary = (fields.step_primary != null && String(fields.step_primary).trim()) || '—';
  const secondary = typeof fields.step_secondary === 'string' && fields.step_secondary.trim() ? fields.step_secondary.trim() : '';
  const tone = fields.tone != null ? String(fields.tone) : 'idle';
  const showTimer = typeof stepElapsedMs === 'number' && stepElapsedMs >= 0;
  return (
    <div className="claw-live-activity claw-trace-task-step" data-claw-activity-tone={tone} role="status">
      {showPulse ? <span className="claw-live-activity-pulse" aria-hidden="true" /> : null}
      <div className="claw-live-activity-copy claw-trace-task-step-inner">
        {runLine ? (
          <div className="claw-trace-task-step-section">
            <span className="claw-trace-task-step-label">Task</span>
            <span className="claw-trace-task-step-text">{runLine}</span>
          </div>
        ) : null}
        <div className="claw-trace-task-step-section">
          <span className="claw-trace-task-step-label">Step</span>
          <span className="claw-trace-task-step-primary">{primary}</span>
          {secondary ? <span className="claw-trace-task-step-secondary">{secondary}</span> : null}
        </div>
        {showTimer ? (
          <div className="claw-trace-task-step-section claw-trace-task-step-timer-row" aria-live="polite">
            <span className="claw-trace-task-step-label">Step time</span>
            <span className="claw-trace-task-step-timer-value">{formatClawStepDuration(stepElapsedMs)}</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}

/**
 * Live duration for the current trace phase (resets when step_count / last step fingerprint changes).
 * @param {Record<string, unknown> | null} trace
 * @param {boolean} active
 */
function useClawStepElapsedMs(trace, active) {
  const phaseKeyRef = useRef('');
  const [anchorMs, setAnchorMs] = useState(null);
  const [, setTick] = useState(0);

  useEffect(() => {
    if (!active || !trace) {
      phaseKeyRef.current = '';
      setAnchorMs(null);
      return;
    }
    const pk = clawTracePhaseKey(trace);
    if (pk !== phaseKeyRef.current) {
      phaseKeyRef.current = pk;
      setAnchorMs(Date.now());
    } else {
      setAnchorMs((prev) => (prev == null ? Date.now() : prev));
    }
  }, [active, trace]);

  useEffect(() => {
    if (!active || !trace) return undefined;
    const id = setInterval(() => setTick((n) => n + 1), 200);
    return () => clearInterval(id);
  }, [active, trace]);

  if (!active || !trace || anchorMs == null) return null;
  return Date.now() - anchorMs;
}

/**
 * @param {{ trace?: Record<string, unknown> | null, capsules?: Array<{ key: string, label: string, title?: string, variant?: string }> | null }} props
 */
function ClawTraceUsageCapsulesRow({ trace, capsules: capsulesProp }) {
  let capsules;
  if (Array.isArray(capsulesProp)) {
    capsules = capsulesProp.filter(
      (c) => c && c.key != null && c.label != null && String(c.label).trim() !== '',
    );
  } else {
    capsules = getClawTraceUsageCapsules(trace).capsules;
  }
  if (!capsules.length) return null;
  return (
    <div className="claw-trace-usage-capsules" role="list" aria-label="Tools and resources in this run">
      {capsules.map((c) => (
        <span
          key={String(c.key)}
          role="listitem"
          className={`claw-trace-usage-capsule claw-trace-usage-capsule--${c.variant || 'tool'}`}
          title={c.title || undefined}
        >
          {c.label}
        </span>
      ))}
    </div>
  );
}

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

function WindDownLinearBar({ endsAt }) {
  const endsRef = useRef(endsAt);
  endsRef.current = endsAt;
  const fillRef = useRef(null);
  const progressRef = useRef(null);

  const expired = endsAt <= Date.now();

  useEffect(() => {
    if (endsAt <= Date.now()) return undefined;

    let cancelled = false;
    let rafId = 0;

    const tick = () => {
      if (cancelled) return;
      const fill = fillRef.current;
      const root = progressRef.current;
      const remaining = Math.max(0, endsRef.current - Date.now());
      const frac = remaining <= 0 ? 0 : Math.min(1, remaining / WIND_DOWN_MS);
      if (fill) {
        fill.style.transform = `scaleX(${frac})`;
      }
      if (root) {
        root.setAttribute('aria-valuenow', String(Math.round(frac * 100)));
      }
      if (remaining > 0) {
        rafId = requestAnimationFrame(tick);
      }
    };

    rafId = requestAnimationFrame(tick);
    return () => {
      cancelled = true;
      cancelAnimationFrame(rafId);
    };
  }, [endsAt]);

  if (expired) return null;

  const frac0 = Math.min(1, (endsAt - Date.now()) / WIND_DOWN_MS);
  const pct0 = Math.round(frac0 * 100);

  return (
    <div className="notification-proxy-winddown">
      <div
        ref={progressRef}
        className="notification-proxy-winddown-bar-bleed"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={pct0}
        aria-label="Saving to history"
      >
        <div className="notification-proxy-winddown-bar-track">
          <div
            ref={fillRef}
            className="notification-proxy-winddown-bar-fill"
            style={{ transform: `scaleX(${frac0})` }}
          />
        </div>
      </div>
      <span className="notification-proxy-winddown-hint">Saving to history…</span>
    </div>
  );
}

function renderLlmWindDownCard(wd, onOpenLlmProxyTrace) {
  const { endsAt, status, model, stepLine } = wd;
  return (
    <div className="proxy-live-notification notification-proxy-embed notification-proxy-embed--winddown">
      <WindDownLinearBar endsAt={endsAt} />
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
        <button type="button" className="coreui-btn coreui-btn-small coreui-btn-ghost" onClick={onOpenLlmProxyTrace}>
          Traces
        </button>
      </div>
    </div>
  );
}

function renderLlmBusyCard(proxyPayload, busyLlm, onOpenLlmProxyTrace) {
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
        <button type="button" className="coreui-btn coreui-btn-small coreui-btn-ghost" onClick={onOpenLlmProxyTrace}>
          Traces
        </button>
      </div>
    </div>
  );
}

function renderClawWindDownCard(endsAt, snap, onOpenClawTraces, onOpenClawJournal, onOpenClawProxyTools) {
  const s = snap;
  const tid = (s.trace_id && String(s.trace_id).slice(0, 8)) || '—';
  const steps = s.step_count;
  const model = s.resolved_model != null && s.resolved_model !== '' ? String(s.resolved_model) : '—';
  const err = s.error ? String(s.error) : '';
  return (
    <div className="claw-live-notification notification-proxy-embed notification-proxy-embed--winddown">
      <WindDownLinearBar endsAt={endsAt} />
      <ClawTraceTaskStepBlock
        showPulse={false}
        fields={{
          run_line: s.run_line,
          step_primary: s.step_primary,
          step_secondary: s.step_secondary,
          tone: s.tone,
        }}
      />
      <ClawTraceUsageCapsulesRow capsules={Array.isArray(s.usage_capsules) ? s.usage_capsules : []} />
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
        <span className="proxy-live-notification-value">{s.elapsed_ms != null ? String(s.elapsed_ms) : '—'}</span>
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
        <button type="button" className="coreui-btn coreui-btn-small coreui-btn-ghost" onClick={onOpenClawTraces}>
          Traces
        </button>
        <button type="button" className="coreui-btn coreui-btn-small coreui-btn-ghost" onClick={onOpenClawJournal}>
          Journal
        </button>
        <button
          type="button"
          className="coreui-btn coreui-btn-small coreui-btn-ghost"
          onClick={onOpenClawProxyTools}
          title="Vendor parity, skills, and agent HTTP settings"
        >
          Tools
        </button>
      </div>
    </div>
  );
}

function ClawLiveActiveCard({ latest, onOpenClawTraces, onOpenClawJournal, onOpenClawProxyTools }) {
  const active = latest.final === false;
  const stepElapsedMs = useClawStepElapsedMs(latest, active);
  const tid = (latest.trace_id && String(latest.trace_id).slice(0, 8)) || '—';
  const steps = latest.step_count;
  const model = latest.resolved_model != null && latest.resolved_model !== '' ? String(latest.resolved_model) : '—';
  const err = latest.error ? String(latest.error) : '';
  const liveFields = getClawTraceNotificationFields(latest);
  return (
    <div className="claw-live-notification notification-proxy-embed">
      {active ? (
        <ClawTraceTaskStepBlock showPulse fields={liveFields} stepElapsedMs={stepElapsedMs} />
      ) : null}
      <ClawTraceUsageCapsulesRow trace={latest} />
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
        <button type="button" className="coreui-btn coreui-btn-small coreui-btn-ghost" onClick={onOpenClawTraces}>
          Traces
        </button>
        <button type="button" className="coreui-btn coreui-btn-small coreui-btn-ghost" onClick={onOpenClawJournal}>
          Journal
        </button>
        <button
          type="button"
          className="coreui-btn coreui-btn-small coreui-btn-ghost"
          onClick={onOpenClawProxyTools}
          title="Vendor parity, skills, and agent HTTP settings"
        >
          Tools
        </button>
      </div>
    </div>
  );
}

/**
 * Polls LLM proxy trace + Claw live buffer; live card while busy, 7s wind-down then persist to History.
 */
export default function ProxiesLiveNotificationBridge({
  onOpenLlmProxyTrace,
  onOpenClawJournal,
  onOpenClawTraces,
  onOpenClawProxyTools,
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
  /** @type {React.MutableRefObject<Map<string, { gen: number, endsAt: number, status: string, model: string, stepLine: string | null, traceIdShort: string }>>} */
  const llmWindDownsRef = useRef(new Map());
  const [llmWindDownsTick, setLlmWindDownsTick] = useState(0);
  /** @type {React.MutableRefObject<Map<string, { gen: number, endsAt: number, snap: Record<string, unknown> }>>} */
  const clawWindDownsRef = useRef(new Map());
  const [clawWindDownsTick, setClawWindDownsTick] = useState(0);

  const bumpLlmWindDowns = useCallback(() => setLlmWindDownsTick((t) => t + 1), []);
  const bumpClawWindDowns = useCallback(() => setClawWindDownsTick((t) => t + 1), []);

  const prevLlmBusyRef = useRef(false);
  const sawClawInFlightRef = useRef(false);
  const lastFreshClawWindDownTidRef = useRef(null);
  const llmWindDownGenRef = useRef(0);
  const clawWindDownGenRef = useRef(0);
  const prevProxySlotIdsRef = useRef(new Set());
  const llmWindDownTimersRef = useRef(new Map());
  const clawWindDownTimersRef = useRef(new Map());

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
    const traceKey = trace && trace.trace_id != null ? String(trace.trace_id) : 'unknown';

    if (busy) {
      clearLiveSuppression(proxyLiveSlotId('llm', traceKey === 'unknown' ? null : traceKey));
      prevLlmBusyRef.current = true;
      return;
    }

    if (prevLlmBusyRef.current && !busy && trace && !llmWindDownsRef.current.has(traceKey)) {
      const model = traceModelFields(trace).headerShort;
      const stepLine = pickLastStepName(trace?.steps);
      const gen = ++llmWindDownGenRef.current;
      llmWindDownsRef.current.set(traceKey, {
        gen,
        endsAt: Date.now() + WIND_DOWN_MS,
        status,
        model,
        stepLine,
        traceIdShort: trace.trace_id != null ? String(trace.trace_id).slice(0, 12) : '',
      });
      bumpLlmWindDowns();
    }

    prevLlmBusyRef.current = busy;
  }, [proxyPayload, bumpLlmWindDowns, clearLiveSuppression]);

  useEffect(() => {
    const c = clawPayload;
    if (!c || c.available === false) return;

    const traces = c.traces;
    const latest = Array.isArray(traces) && traces.length > 0 ? traces[0] : null;

    if (latest && latest.final === false) {
      const tid = latest.trace_id != null ? String(latest.trace_id) : '';
      if (tid) clearLiveSuppression(proxyLiveSlotId('claw', tid));
      else clearLiveSuppression(proxyLiveSlotId('claw', null));
      sawClawInFlightRef.current = true;
      return;
    }

    if (latest && latest.final === true) {
      const tid = latest.trace_id != null ? String(latest.trace_id) : '';
      const edgeWindDown = sawClawInFlightRef.current === true && tid && !clawWindDownsRef.current.has(tid);
      const ts = Number(latest.ts_ms);
      const ageMs = Number.isFinite(ts) ? Date.now() - ts : Infinity;
      const freshFinalWindDown =
        tid &&
        !clawWindDownsRef.current.has(tid) &&
        !edgeWindDown &&
        ageMs >= 0 &&
        ageMs < 12_000 &&
        lastFreshClawWindDownTidRef.current !== tid;

      if (edgeWindDown || freshFinalWindDown) {
        if (freshFinalWindDown) {
          lastFreshClawWindDownTidRef.current = tid;
        }
        const gen = ++clawWindDownGenRef.current;
        const nf = getClawTraceNotificationFields(latest);
        const usage = getClawTraceUsageCapsules(latest);
        clawWindDownsRef.current.set(tid, {
          gen,
          endsAt: Date.now() + WIND_DOWN_MS,
          snap: {
            trace_id: latest.trace_id,
            step_count: latest.step_count,
            elapsed_ms: latest.elapsed_ms,
            resolved_model: latest.resolved_model,
            error: latest.error,
            run_line: nf.run_line,
            step_primary: nf.step_primary,
            step_secondary: nf.step_secondary,
            tone: nf.tone,
            usage_capsules: usage.capsules,
          },
        });
        bumpClawWindDowns();
      }
      sawClawInFlightRef.current = false;
      return;
    }

    sawClawInFlightRef.current = false;
  }, [clawPayload, bumpClawWindDowns, clearLiveSuppression]);

  useEffect(() => {
    const m = llmWindDownsRef.current;
    const scheduled = llmWindDownTimersRef.current;
    m.forEach((wd, traceKey) => {
      if (scheduled.has(traceKey)) return;
      const delay = Math.max(0, wd.endsAt - Date.now());
      const myGen = wd.gen;
      const myEndsAt = wd.endsAt;
      const slotId = proxyLiveSlotId('llm', traceKey === 'unknown' ? null : traceKey);
      const t = setTimeout(() => {
        scheduled.delete(traceKey);
        void (async () => {
          try {
            if (!sessionId) return;
            const cur = llmWindDownsRef.current.get(traceKey);
            if (!cur || cur.gen !== myGen || cur.endsAt !== myEndsAt) return;
            const parts = [wd.model && `Model: ${wd.model}`, wd.status && `Last status: ${wd.status}`].filter(Boolean);
            if (wd.stepLine) parts.push(`Step: ${wd.stepLine}`);
            if (wd.traceIdShort) parts.push(`Trace: ${wd.traceIdShort}`);
            await persistNotification({
              kind: 'event',
              source: 'rag-fusion-proxy',
              title: 'RAG Fusion Proxy finished',
              message: parts.join(' · ').slice(0, 800),
              metadata: { historyOnly: true },
            });
          } catch (e) {
            console.error('NotificationCenter: LLM wind-down persist failed', e);
          }
        })();
        const cur = llmWindDownsRef.current.get(traceKey);
        if (cur && cur.gen === myGen && cur.endsAt === myEndsAt) {
          llmWindDownsRef.current.delete(traceKey);
          bumpLlmWindDowns();
        }
        clearLiveActivity(slotId);
      }, delay);
      scheduled.set(traceKey, t);
    });
    [...scheduled.keys()].forEach((key) => {
      if (!m.has(key)) {
        clearTimeout(scheduled.get(key));
        scheduled.delete(key);
      }
    });
  }, [llmWindDownsTick, sessionId, persistNotification, clearLiveActivity, bumpLlmWindDowns]);

  useEffect(() => {
    const m = clawWindDownsRef.current;
    const scheduled = clawWindDownTimersRef.current;
    m.forEach((wd, traceKey) => {
      if (scheduled.has(traceKey)) return;
      const delay = Math.max(0, wd.endsAt - Date.now());
      const myGen = wd.gen;
      const myEndsAt = wd.endsAt;
      const snap = wd.snap;
      const slotId = proxyLiveSlotId('claw', traceKey || null);
      const t = setTimeout(() => {
        scheduled.delete(traceKey);
        void (async () => {
          try {
            if (!sessionId) return;
            const cur = clawWindDownsRef.current.get(traceKey);
            if (!cur || cur.gen !== myGen || cur.endsAt !== myEndsAt) return;
            const tidShort = snap.trace_id != null ? String(snap.trace_id).slice(0, 8) : '';
            const err = snap.error ? String(snap.error) : '';
            const task = typeof snap.run_line === 'string' && snap.run_line.trim() ? snap.run_line.trim() : '';
            const stepP =
              typeof snap.step_primary === 'string' && snap.step_primary.trim() ? snap.step_primary.trim() : '';
            const stepS =
              typeof snap.step_secondary === 'string' && snap.step_secondary.trim() ? snap.step_secondary.trim() : '';
            const capLine =
              Array.isArray(snap.usage_capsules) && snap.usage_capsules.length > 0
                ? snap.usage_capsules
                    .map((c) => (c && c.label != null ? String(c.label) : ''))
                    .filter(Boolean)
                    .join(', ')
                : '';
            const msg = [
              task && `Task: ${task.slice(0, 200)}`,
              stepP && `Step: ${stepP.slice(0, 160)}${stepS ? ` — ${stepS.slice(0, 160)}` : ''}`,
              capLine && `Tools: ${capLine.slice(0, 240)}`,
              tidShort && `Trace ${tidShort}`,
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
              title: err ? 'Claw Code finished with error' : 'Claw Code finished',
              message: msg.slice(0, 800),
              metadata: { historyOnly: true },
            });
          } catch (e) {
            console.error('NotificationCenter: Claw wind-down persist failed', e);
          }
        })();
        const cur = clawWindDownsRef.current.get(traceKey);
        if (cur && cur.gen === myGen && cur.endsAt === myEndsAt) {
          clawWindDownsRef.current.delete(traceKey);
          bumpClawWindDowns();
        }
        clearLiveActivity(slotId);
      }, delay);
      scheduled.set(traceKey, t);
    });
    [...scheduled.keys()].forEach((key) => {
      if (!m.has(key)) {
        clearTimeout(scheduled.get(key));
        scheduled.delete(key);
      }
    });
  }, [clawWindDownsTick, sessionId, persistNotification, clearLiveActivity, bumpClawWindDowns]);

  useEffect(
    () => () => {
      llmWindDownTimersRef.current.forEach((tid) => clearTimeout(tid));
      llmWindDownTimersRef.current.clear();
      clawWindDownTimersRef.current.forEach((tid) => clearTimeout(tid));
      clawWindDownTimersRef.current.clear();
    },
    [],
  );

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

  useEffect(() => {
    clearLiveActivity(LEGACY_LLM_LIVE_ID);
    clearLiveActivity(LEGACY_CLAW_LIVE_ID);
  }, [clearLiveActivity]);

  const proxyLiveRows = useMemo(() => {
    /** @type {{ id: string, source: string, node: React.ReactNode, headerLeading?: React.ReactNode }[]} */
    const rows = [];
    const llmWd = llmWindDownsRef.current;
    const clawWd = clawWindDownsRef.current;

    if (busyLlm && proxyPayload?.trace) {
      const tk = proxyPayload.trace.trace_id != null ? String(proxyPayload.trace.trace_id) : 'unknown';
      rows.push({
        id: proxyLiveSlotId('llm', tk === 'unknown' ? null : tk),
        source: 'rag-fusion-proxy',
        node: renderLlmBusyCard(proxyPayload, busyLlm, onOpenLlmProxyTrace),
      });
    }
    llmWd.forEach((wd, traceKey) => {
      rows.push({
        id: proxyLiveSlotId('llm', traceKey === 'unknown' ? null : traceKey),
        source: 'rag-fusion-proxy',
        node: renderLlmWindDownCard(wd, onOpenLlmProxyTrace),
      });
    });

    const c = clawPayload;
    if (c && c.available !== false && clawInFlight) {
      const traces = c.traces;
      const latest = Array.isArray(traces) && traces.length > 0 ? traces[0] : null;
      if (latest && latest.trace_id != null) {
        const tk = String(latest.trace_id);
        rows.push({
          id: proxyLiveSlotId('claw', tk),
          source: 'claw-proxy',
          headerLeading: CLAW_CODE_HEADER_ICON,
          node: (
            <ClawLiveActiveCard
              latest={latest}
              onOpenClawTraces={onOpenClawTraces}
              onOpenClawJournal={onOpenClawJournal}
              onOpenClawProxyTools={onOpenClawProxyTools}
            />
          ),
        });
      }
    }
    clawWd.forEach((wd, traceKey) => {
      rows.push({
        id: proxyLiveSlotId('claw', traceKey || null),
        source: 'claw-proxy',
        headerLeading: CLAW_CODE_HEADER_ICON,
        node: renderClawWindDownCard(wd.endsAt, wd.snap, onOpenClawTraces, onOpenClawJournal, onOpenClawProxyTools),
      });
    });
    return rows;
  }, [
    busyLlm,
    proxyPayload,
    llmWindDownsTick,
    clawWindDownsTick,
    clawPayload,
    clawInFlight,
    onOpenLlmProxyTrace,
    onOpenClawTraces,
    onOpenClawJournal,
    onOpenClawProxyTools,
  ]);

  useEffect(() => {
    const next = new Set();
    for (const row of proxyLiveRows) {
      if (liveSuppressedIds.includes(row.id)) continue;
      setLiveActivity(
        row.id,
        row.source,
        row.node,
        row.headerLeading != null ? { headerLeading: row.headerLeading } : undefined,
      );
      next.add(row.id);
    }
    prevProxySlotIdsRef.current.forEach((id) => {
      if (!next.has(id)) clearLiveActivity(id);
    });
    prevProxySlotIdsRef.current = next;
  }, [proxyLiveRows, liveSuppressedIds, setLiveActivity, clearLiveActivity]);

  useEffect(
    () => () => {
      prevProxySlotIdsRef.current.forEach((id) => clearLiveActivity(id));
      prevProxySlotIdsRef.current.clear();
    },
    [clearLiveActivity],
  );

  return null;
}
