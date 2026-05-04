import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getProxyTraceCurrent } from '../services/api';
import {
  getOllamaModelBrandKey,
  OLLAMA_BRAND_ICON_URL,
} from '../utils/ollamaModelBrandIcons';
import { traceModelFields } from '../utils/proxyTraceModel';
import CoreUIButton from './CoreUIButton';
import { useNotificationCenter } from './NotificationCenterContext';

const POLL_MS = 1000;
const WIND_DOWN_MS = 7_000;

const LEGACY_LLM_LIVE_ID = 'llm-proxy-live';

/** One live card per explicit chain key (fallback: trace id). */
function proxyLiveSlotId(slotKey) {
  const raw = slotKey != null && String(slotKey).trim() !== '' ? String(slotKey).trim() : 'unknown';
  const safe = raw.replace(/[^a-zA-Z0-9_-]+/g, '_').slice(0, 72);
  return `llm-proxy-live-${safe}`;
}

function nonEmptyString(value) {
  if (value == null) return '';
  const s = String(value).trim();
  return s !== '' ? s : '';
}

function traceChainId(trace) {
  const req = trace && typeof trace === 'object' && trace.request && typeof trace.request === 'object'
    ? trace.request
    : null;
  return nonEmptyString(req?.trace_chain_id);
}

function traceSlotKey(trace) {
  return nonEmptyString(trace?.trace_id) || traceChainId(trace) || 'unknown';
}

function traceShortId(value) {
  const s = nonEmptyString(value);
  return s ? s.slice(0, 12) : '';
}

function numOrNull(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : null;
}

function computeGenTokensPerSecond(trace) {
  const response = trace && typeof trace === 'object' && trace.response && typeof trace.response === 'object'
    ? trace.response
    : {};
  const ollama = trace && typeof trace === 'object' && trace.ollama && typeof trace.ollama === 'object'
    ? trace.ollama
    : {};
  const tokensEst = ollama.tokens_estimates && typeof ollama.tokens_estimates === 'object'
    ? ollama.tokens_estimates
    : {};

  const latencyMs = numOrNull(response.latency_ms);
  const completionEstimated = numOrNull(tokensEst.completion_tokens_estimated);
  if (latencyMs != null && latencyMs > 0 && completionEstimated != null && completionEstimated > 0) {
    return { value: (completionEstimated / latencyMs) * 1000, source: 'tokens_estimates' };
  }

  const steps = Array.isArray(trace?.steps) ? trace.steps : [];
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const step = steps[i];
    const name = nonEmptyString(step?.name);
    if (!name.startsWith('ollama_chat') && !name.startsWith('provider_chat')) continue;
    const outTok = numOrNull(step?.tokens_out_est);
    const durMs = numOrNull(step?.duration_ms);
    if (outTok != null && outTok > 0 && durMs != null && durMs > 0) {
      return { value: (outTok / durMs) * 1000, source: 'step_tokens_out_est' };
    }
  }

  const evalCount = numOrNull(response.eval_count) ?? numOrNull(response.ollama_eval_count);
  if (latencyMs != null && latencyMs > 0 && evalCount != null && evalCount > 0) {
    return { value: (evalCount / latencyMs) * 1000, source: 'eval_count' };
  }
  return null;
}

function genTpsSourceTitle(source) {
  if (source === 'tokens_estimates') return 'Source: trace.ollama.tokens_estimates.completion_tokens_estimated';
  if (source === 'step_tokens_out_est') return 'Source: last provider_chat* step.tokens_out_est / step.duration_ms';
  if (source === 'eval_count') return 'Source: trace.response.eval_count';
  return 'Source: unknown';
}

function ModelValue({ model, brandKey }) {
  const resolvedBrandKey = brandKey || getOllamaModelBrandKey(model);
  const brandIconUrl = resolvedBrandKey ? OLLAMA_BRAND_ICON_URL[resolvedBrandKey] : null;
  return (
    <span className="proxy-live-notification-model-value">
      {brandIconUrl ? (
        <img
          className="proxy-live-notification-model-icon"
          src={brandIconUrl}
          alt=""
          width={16}
          height={16}
          loading="lazy"
          decoding="async"
          title={`Provider: ${resolvedBrandKey}`}
        />
      ) : null}
      <span className="proxy-live-notification-value proxy-live-notification-mono">{model}</span>
    </span>
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

function buildStepCapsules(steps) {
  if (!Array.isArray(steps) || steps.length === 0) return [];
  let currentIndex = -1;
  for (let i = steps.length - 1; i >= 0; i -= 1) {
    const s = steps[i];
    if (s && s.duration_ms == null) {
      currentIndex = i;
      break;
    }
  }
  const capsules = [];
  for (let i = 0; i < steps.length; i += 1) {
    const s = steps[i];
    const name = s?.name != null && s.name !== '' ? String(s.name) : null;
    if (!name) continue;
    const completed = s?.duration_ms != null;
    const current = i === currentIndex;
    if (!completed && !current) continue;
    capsules.push({ name, state: current ? 'current' : 'completed' });
  }
  return capsules;
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
  const { endsAt, status, model, traceId, chainId, steps, brandKey } = wd;
  const stepCapsules = buildStepCapsules(steps);
  return (
    <div className="proxy-live-notification notification-proxy-embed notification-proxy-embed--winddown">
      <WindDownLinearBar endsAt={endsAt} />
      <div className="proxy-live-notification-status">
        <span className="proxy-live-notification-label">Status</span>
        <span className="proxy-live-notification-value">{status}</span>
      </div>
      <div className="proxy-live-notification-row">
        <span className="proxy-live-notification-label">Model</span>
        <ModelValue model={model} brandKey={brandKey} />
      </div>
      {traceId ? (
        <div className="proxy-live-notification-row">
          <span className="proxy-live-notification-label">Track ID</span>
          <span className="proxy-live-notification-value proxy-live-notification-mono">{traceId}</span>
        </div>
      ) : null}
      {chainId ? (
        <div className="proxy-live-notification-row">
          <span className="proxy-live-notification-label">Chain</span>
          <span className="proxy-live-notification-value proxy-live-notification-mono">{chainId}</span>
        </div>
      ) : null}
      {stepCapsules.length ? (
        <div className="proxy-live-notification-steps" aria-label="Trace steps">
          {stepCapsules.map((step, idx) => (
            <span key={`${step.name}-${idx}`} className={`proxy-live-step-capsule proxy-live-step-capsule--${step.state}`}>
              {step.name}
            </span>
          ))}
        </div>
      ) : null}
      <div className="proxy-live-notification-actions">
        <CoreUIButton size="sm" variant="ghost" onClick={onOpenLlmProxyTrace}>
          Traces
        </CoreUIButton>
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
  const brandKey = trace?.response?.brand_key;
  const stepCapsules = buildStepCapsules(trace?.steps);
  const traceId = trace?.trace_id != null && trace.trace_id !== '' ? String(trace.trace_id) : '';
  const chainId = traceChainId(trace);
  const genTps = computeGenTokensPerSecond(trace);
  const tpsDisplay = genTps != null && genTps.value > 0 ? `${genTps.value.toFixed(2)} tok/s` : null;
  const tpsTitle = genTps != null ? genTpsSourceTitle(genTps.source) : null;
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
        <ModelValue model={model} brandKey={brandKey} />
      </div>
      {traceId ? (
        <div className="proxy-live-notification-row">
          <span className="proxy-live-notification-label">Track ID</span>
          <span className="proxy-live-notification-value proxy-live-notification-mono">{traceId}</span>
        </div>
      ) : null}
      {chainId ? (
        <div className="proxy-live-notification-row">
          <span className="proxy-live-notification-label">Chain</span>
          <span className="proxy-live-notification-value proxy-live-notification-mono">{chainId}</span>
        </div>
      ) : null}
      {tpsDisplay ? (
        <div className="proxy-live-notification-row">
          <span className="proxy-live-notification-label">Gen tok/s</span>
          <span
            className="proxy-live-notification-value proxy-live-notification-mono"
            title={tpsTitle || undefined}
          >
            {tpsDisplay}
          </span>
        </div>
      ) : null}
      {stepCapsules.length ? (
        <div className="proxy-live-notification-steps" aria-label="Trace steps">
          {stepCapsules.map((step, idx) => (
            <span key={`${step.name}-${idx}`} className={`proxy-live-step-capsule proxy-live-step-capsule--${step.state}`}>
              {step.name}
            </span>
          ))}
        </div>
      ) : null}
      <div className="proxy-live-notification-actions">
        <CoreUIButton size="sm" variant="ghost" onClick={onOpenLlmProxyTrace}>
          Traces
        </CoreUIButton>
      </div>
    </div>
  );
}

function payloadStatus(proxyPayload) {
  return (
    proxyPayload?.status != null && proxyPayload.status !== '' ? String(proxyPayload.status) : 'Idle'
  ).trim();
}

function payloadBusy(proxyPayload) {
  return payloadStatus(proxyPayload) !== 'Idle';
}

function payloadActiveTraces(proxyPayload) {
  if (!proxyPayload) return [];
  if (Array.isArray(proxyPayload.active_traces) && proxyPayload.active_traces.length) {
    return proxyPayload.active_traces.filter((trace) => trace && typeof trace === 'object');
  }
  if (payloadBusy(proxyPayload) && proxyPayload.trace && typeof proxyPayload.trace === 'object') {
    return [proxyPayload.trace];
  }
  return [];
}

function ragCollectionIssueFromTrace(trace) {
  const issue = trace?.rag?.collection_issue;
  if (!issue || typeof issue !== 'object') return null;
  const code = nonEmptyString(issue.code) || 'rag_collection_issue';
  const collection = nonEmptyString(issue.collection_name);
  const source = nonEmptyString(issue.collection_source);
  const message = nonEmptyString(issue.message) || 'Choose a Qdrant collection in RAG / Qdrant before using RAG.';
  return {
    code,
    collection,
    source,
    title: nonEmptyString(issue.title) || 'RAG collection is not selected',
    message,
    aggregationKey: ['rag-collection', code, collection || source || 'default'].join(':'),
    metadata: {
      code,
      collection_name: collection || null,
      collection_source: source || null,
      trace_id: nonEmptyString(trace?.trace_id) || null,
      available_collections: Array.isArray(issue.available_collections) ? issue.available_collections : [],
    },
  };
}

/**
 * Polls LLM proxy trace; live card while busy, 7s wind-down then persist to History.
 */
export default function ProxiesLiveNotificationBridge({
  onOpenLlmProxyTrace,
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
  /** @type {React.MutableRefObject<Map<string, { gen: number, endsAt: number, status: string, model: string, stepLine: string | null, traceIdShort: string, traceId: string, steps: unknown[] }>>} */
  const llmWindDownsRef = useRef(new Map());
  const [llmWindDownsTick, setLlmWindDownsTick] = useState(0);

  const bumpLlmWindDowns = useCallback(() => setLlmWindDownsTick((t) => t + 1), []);

  const prevActiveProxyTracesRef = useRef(new Map());
  const llmWindDownGenRef = useRef(0);
  const prevProxySlotIdsRef = useRef(new Set());
  const llmWindDownTimersRef = useRef(new Map());
  const notifiedCollectionIssuesRef = useRef(new Set());

  useEffect(() => {
    let cancelled = false;

    const tick = async () => {
      try {
        const p = await getProxyTraceCurrent();
        if (!cancelled) setProxyPayload(p || null);
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

    const status = payloadStatus(p);
    const activeTraces = payloadActiveTraces(p);
    const nextActive = new Map();
    activeTraces.forEach((trace) => {
      const slotKey = traceSlotKey(trace);
      nextActive.set(slotKey, trace);
      clearLiveSuppression(proxyLiveSlotId(slotKey === 'unknown' ? null : slotKey));
      if (llmWindDownsRef.current.has(slotKey)) {
        llmWindDownsRef.current.delete(slotKey);
        const scheduled = llmWindDownTimersRef.current;
        const tid = scheduled.get(slotKey);
        if (tid != null) {
          clearTimeout(tid);
          scheduled.delete(slotKey);
        }
        bumpLlmWindDowns();
      }
    });

    prevActiveProxyTracesRef.current.forEach((trace, slotKey) => {
      if (nextActive.has(slotKey)) return;
      const model = traceModelFields(trace).headerShort;
      const stepLine = pickLastStepName(trace?.steps);
      const chainIdFull = traceChainId(trace);
      const chainIdShort = traceShortId(chainIdFull);
      const gen = ++llmWindDownGenRef.current;
      llmWindDownsRef.current.set(slotKey, {
        gen,
        endsAt: Date.now() + WIND_DOWN_MS,
        status,
        model,
        brandKey: trace?.response?.brand_key,
        stepLine,
        traceIdShort: traceShortId(trace?.trace_id),
        traceId: nonEmptyString(trace?.trace_id),
        chainIdShort,
        chainId: chainIdFull,
        steps: Array.isArray(trace.steps) ? trace.steps : [],
      });
      bumpLlmWindDowns();
    });

    prevActiveProxyTracesRef.current = nextActive;
  }, [proxyPayload, bumpLlmWindDowns, clearLiveSuppression]);

  useEffect(() => {
    if (!proxyPayload || !sessionId) return;
    const traces = [
      proxyPayload.trace,
      ...(Array.isArray(proxyPayload.active_traces) ? proxyPayload.active_traces : []),
    ].filter((trace) => trace && typeof trace === 'object');
    traces.forEach((trace) => {
      const issue = ragCollectionIssueFromTrace(trace);
      if (!issue) return;
      if (notifiedCollectionIssuesRef.current.has(issue.aggregationKey)) return;
      notifiedCollectionIssuesRef.current.add(issue.aggregationKey);
      void persistNotification({
        kind: 'error',
        source: 'rag-fusion-proxy',
        title: issue.title,
        message: issue.message,
        metadata: issue.metadata,
        aggregation_key: issue.aggregationKey,
      });
    });
  }, [proxyPayload, sessionId, persistNotification]);

  useEffect(() => {
    const m = llmWindDownsRef.current;
    const scheduled = llmWindDownTimersRef.current;
    m.forEach((wd, traceKey) => {
      if (scheduled.has(traceKey)) return;
      const delay = Math.max(0, wd.endsAt - Date.now());
      const myGen = wd.gen;
      const myEndsAt = wd.endsAt;
      const slotId = proxyLiveSlotId(traceKey === 'unknown' ? null : traceKey);
      const t = setTimeout(() => {
        scheduled.delete(traceKey);
        void (async () => {
          try {
            if (!sessionId) return;
            const cur = llmWindDownsRef.current.get(traceKey);
            if (!cur || cur.gen !== myGen || cur.endsAt !== myEndsAt) return;
            const parts = [wd.model && `Model: ${wd.model}`, wd.status && `Last status: ${wd.status}`].filter(Boolean);
            if (wd.stepLine) parts.push(`Step: ${wd.stepLine}`);
            if (wd.chainIdShort) parts.push(`Chain: ${wd.chainIdShort}`);
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

  useEffect(
    () => () => {
      llmWindDownTimersRef.current.forEach((tid) => clearTimeout(tid));
      llmWindDownTimersRef.current.clear();
    },
    [],
  );

  const busyLlm = useMemo(() => {
    return payloadActiveTraces(proxyPayload).length > 0 || payloadBusy(proxyPayload);
  }, [proxyPayload]);

  useEffect(() => {
    clearLiveActivity(LEGACY_LLM_LIVE_ID);
  }, [clearLiveActivity]);

  const proxyLiveRows = useMemo(() => {
    /** @type {{ id: string, source: string, node: React.ReactNode, headerLeading?: React.ReactNode }[]} */
    const rows = [];
    const llmWd = llmWindDownsRef.current;

    const activeTraces = payloadActiveTraces(proxyPayload);
    activeTraces.forEach((trace) => {
      const tk = traceSlotKey(trace);
      rows.push({
        id: proxyLiveSlotId(tk === 'unknown' ? null : tk),
        source: 'rag-fusion-proxy',
        node: renderLlmBusyCard({ ...proxyPayload, trace }, true, onOpenLlmProxyTrace),
      });
    });
    llmWd.forEach((wd, traceKey) => {
      rows.push({
        id: proxyLiveSlotId(traceKey === 'unknown' ? null : traceKey),
        source: 'rag-fusion-proxy',
        node: renderLlmWindDownCard(wd, onOpenLlmProxyTrace),
      });
    });

    return rows;
  }, [
    busyLlm,
    proxyPayload,
    llmWindDownsTick,
    onOpenLlmProxyTrace,
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
