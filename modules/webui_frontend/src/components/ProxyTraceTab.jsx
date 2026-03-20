import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  getProxyLogs,
  getProxyTraceCurrent,
  getSettings,
  updateSettings,
} from '../services/api';
import './ProxyTraceTab.css';

const LIVE_POLL_MS = 1000;
const HISTORY_LIMIT = 20;

function safeJsonParse(maybeJson) {
  if (!maybeJson) return null;
  if (typeof maybeJson === 'string') {
    try {
      return JSON.parse(maybeJson);
    } catch {
      return null;
    }
  }
  return maybeJson;
}

function formatTs(ts) {
  if (!ts) return 'N/A';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts);
  }
}

function toPct(n, d) {
  if (d == null || d === 0) return null;
  const v = (n / d) * 100;
  if (!Number.isFinite(v)) return null;
  return Math.max(0, Math.min(999, v));
}

export default function ProxyTraceTab() {
  const [mode, setMode] = useState('live'); // 'live' | 'history'
  const [livePayload, setLivePayload] = useState({ trace: null, status: null, updated_at: null });
  const [historyTraces, setHistoryTraces] = useState([]); // { trace, meta }
  const [selectedHistoryIndex, setSelectedHistoryIndex] = useState(null);
  const [selectedStepIndex, setSelectedStepIndex] = useState(0);

  const [modelMaxContextTokens, setModelMaxContextTokens] = useState(0);
  const [modelMaxContextTokensDraft, setModelMaxContextTokensDraft] = useState('');
  const [savingModelMax, setSavingModelMax] = useState(false);

  const pollTimerRef = useRef(null);

  const selectedTrace = useMemo(() => {
    if (mode === 'live') return livePayload?.trace || null;
    if (selectedHistoryIndex == null) return null;
    return historyTraces[selectedHistoryIndex]?.trace || null;
  }, [mode, livePayload, selectedHistoryIndex, historyTraces]);

  const steps = selectedTrace?.steps || [];

  useEffect(() => {
    if (mode !== 'live') return;
    let cancelled = false;

    const poll = async () => {
      try {
        const payload = await getProxyTraceCurrent();
        if (cancelled) return;
        setLivePayload(payload || { trace: null, status: null, updated_at: null });
      } catch {
        // ignore (UI should keep running)
      }
    };

    poll();
    pollTimerRef.current = setInterval(poll, LIVE_POLL_MS);
    return () => {
      cancelled = true;
      if (pollTimerRef.current) clearInterval(pollTimerRef.current);
    };
  }, [mode]);

  useEffect(() => {
    if (mode !== 'history') return;

    let cancelled = false;
    const load = async () => {
      try {
        const data = await getProxyLogs({ limit: HISTORY_LIMIT });
        if (cancelled) return;
        const logs = data?.logs || [];

        const mapped = logs
          .map((log) => {
            const metadata = safeJsonParse(log?.metadata) || log?.metadata || {};
            const trace = metadata?.trace || null;
            if (!trace) return null;
            return {
              trace,
              meta: {
                log_id: log?.id,
                timestamp: log?.timestamp,
                user_query: metadata?.user_query,
                latency_ms: metadata?.latency_ms,
                trace_id: metadata?.trace_id || trace?.trace_id,
              },
            };
          })
          .filter(Boolean);

        mapped.sort((a, b) => {
          const at = a?.meta?.timestamp || a?.trace?.created_at;
          const bt = b?.meta?.timestamp || b?.trace?.created_at;
          const av = at ? new Date(at).getTime() : 0;
          const bv = bt ? new Date(bt).getTime() : 0;
          return bv - av;
        });

        setHistoryTraces(mapped);
        setSelectedHistoryIndex(mapped.length ? 0 : null);
        setSelectedStepIndex(0);
      } catch {
        if (!cancelled) setHistoryTraces([]);
      }
    };

    load();
    return () => {
      cancelled = true;
    };
  }, [mode]);

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const s = await getSettings();
        const raw = s?.model_max_context_tokens;
        const v = raw == null || raw === '' ? 0 : Number(raw);
        if (Number.isFinite(v)) {
          setModelMaxContextTokens(v);
          setModelMaxContextTokensDraft(String(v));
        }
      } catch {
        // ignore
      }
    };
    loadSettings();
  }, []);

  useEffect(() => {
    setSelectedStepIndex(0);
  }, [selectedTrace?.trace_id]);

  const graph = useMemo(() => {
    const rag = selectedTrace?.rag?.context;
    const ragUsedPct = rag?.context_budget_chars
      ? toPct(rag?.context_chars_used || 0, rag?.context_budget_chars || 0)
      : null;

    const totalTokens = selectedTrace?.ollama?.tokens_estimates?.total_tokens_estimated;
    const modelPct = modelMaxContextTokens > 0 ? toPct(totalTokens || 0, modelMaxContextTokens) : null;
    return { ragUsedPct, modelPct, totalTokens };
  }, [selectedTrace, modelMaxContextTokens]);

  const selectedStep = steps[selectedStepIndex] || null;

  const ragChunks = selectedTrace?.rag?.context?.chunks || [];
  const ragTimings = selectedTrace?.rag?.timings || {};
  const internet = selectedTrace?.internet || {};

  const commitModelMax = async () => {
    const draft = Number(modelMaxContextTokensDraft);
    if (!Number.isFinite(draft) || draft <= 0) return;

    setSavingModelMax(true);
    try {
      await updateSettings({ model_max_context_tokens: draft });
      setModelMaxContextTokens(draft);
    } catch {
      // ignore
    } finally {
      setSavingModelMax(false);
    }
  };

  return (
    <div className="proxy-trace-tab">
      <div className="proxy-trace-header">
        <div className="mode-toggle">
          <button
            className={`mode-btn ${mode === 'live' ? 'active' : ''}`}
            onClick={() => setMode('live')}
            type="button"
          >
            Live
          </button>
          <button
            className={`mode-btn ${mode === 'history' ? 'active' : ''}`}
            onClick={() => setMode('history')}
            type="button"
          >
            History
          </button>
        </div>

        {mode === 'live' ? (
          <div className="live-meta">
            <div>
              <span className="label">Status:</span> {livePayload?.status || 'N/A'}
            </div>
            <div>
              <span className="label">Updated:</span> {formatTs(livePayload?.updated_at)}
            </div>
          </div>
        ) : (
          <div className="live-meta">
            <div>
              <span className="label">Loaded:</span> {historyTraces.length} traces (last {HISTORY_LIMIT})
            </div>
          </div>
        )}
      </div>

      <div className="proxy-trace-grid">
        <div className="proxy-trace-left">
          <div className="card">
            <div className="card-title">Context Usage</div>
            <div className="usage-row">
              <div className="usage-label">RAG budget used</div>
              <div className="usage-value">
                {graph.ragUsedPct == null ? 'N/A' : `${graph.ragUsedPct.toFixed(1)}%`}
              </div>
            </div>
            <div className="usage-bar">
              <div
                className="usage-bar-fill"
                style={{
                  width: graph.ragUsedPct == null ? '0%' : `${Math.min(100, graph.ragUsedPct)}%`,
                }}
              />
            </div>

            <div className="usage-row" style={{ marginTop: 10 }}>
              <div className="usage-label">Model window used</div>
              <div className="usage-value">
                {graph.modelPct == null ? 'N/A' : `${graph.modelPct.toFixed(1)}%`}
              </div>
            </div>
            <div className="usage-bar usage-bar-secondary">
              <div
                className="usage-bar-fill"
                style={{
                  width: graph.modelPct == null ? '0%' : `${Math.min(100, graph.modelPct)}%`,
                }}
              />
            </div>

            <div className="usage-hints">
              <div className="hint-line">
                <span className="label">Total tokens (est):</span> {graph.totalTokens ?? 'N/A'}
              </div>
              <div className="hint-line">
                <span className="label">Model max tokens:</span> {modelMaxContextTokens || 'N/A'}
              </div>
            </div>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <div className="card-title">Model Max Context Tokens</div>
            <div className="form-row">
              <input
                className="text-input"
                value={modelMaxContextTokensDraft}
                onChange={(e) => setModelMaxContextTokensDraft(e.target.value)}
                placeholder="e.g. 8192"
                inputMode="numeric"
              />
              <button
                type="button"
                className="btn"
                disabled={savingModelMax}
                onClick={commitModelMax}
              >
                {savingModelMax ? 'Saving...' : 'Save'}
              </button>
            </div>
          </div>

          <div className="card" style={{ marginTop: 12 }}>
            <div className="card-title">{mode === 'live' ? 'Steps (Live)' : 'Steps (Selected Trace)'}</div>
            <div className="steps-list">
              {steps.length ? (
                steps.map((s, idx) => (
                  <button
                    key={`${s.name}-${idx}`}
                    type="button"
                    className={`step-item ${idx === selectedStepIndex ? 'active' : ''}`}
                    onClick={() => setSelectedStepIndex(idx)}
                  >
                    <div className="step-name">{s.name}</div>
                    <div className="step-sub">
                      {s.duration_ms != null ? `${s.duration_ms} ms` : ''}
                    </div>
                  </button>
                ))
              ) : (
                <div className="empty">No trace yet.</div>
              )}
            </div>
          </div>
        </div>

        <div className="proxy-trace-right">
          <div className="card">
            <div className="card-title">Trace Details</div>
            {!selectedTrace ? (
              <div className="empty">Select a trace to view internals.</div>
            ) : (
              <div className="trace-details">
                <div className="detail-row">
                  <span className="label">Trace ID:</span> {selectedTrace.trace_id || 'N/A'}
                </div>
                <div className="detail-row">
                  <span className="label">Created:</span> {formatTs(selectedTrace.created_at)}
                </div>

                <div className="separator" />

                {selectedStep ? (
                  <>
                    <div className="detail-row">
                      <span className="label">Selected Step:</span> {selectedStep.name}
                    </div>
                    <div className="detail-row">
                      <span className="label">Duration:</span> {selectedStep.duration_ms ?? 'N/A'} ms
                    </div>
                    <div className="detail-row">
                      <span className="label">Tokens in (est):</span> {selectedStep.tokens_in_est ?? 'N/A'}
                    </div>
                    <div className="detail-row">
                      <span className="label">Tokens out (est):</span> {selectedStep.tokens_out_est ?? 0}
                    </div>
                  </>
                ) : null}

                <div className="separator" />

                <div className="section-title">RAG Context</div>
                {selectedTrace.rag?.context ? (
                  <>
                    <div className="detail-row">
                      <span className="label">Context chars used:</span>{' '}
                      {selectedTrace.rag.context.context_chars_used}
                    </div>
                    <div className="detail-row">
                      <span className="label">Context budget chars (max):</span>{' '}
                      {selectedTrace.rag.context.context_budget_chars}
                    </div>
                    <div className="detail-row">
                      <span className="label">Chunks in context:</span>{' '}
                      {selectedTrace.rag.context.chunks?.length ?? 0}
                    </div>

                    <div className="chunk-list">
                      {ragChunks.map((c, i) => (
                        <div key={`${c.url || 'chunk'}-${i}`} className="chunk-item">
                          <div className="chunk-head">
                            <span className="chunk-label">{c.label || 'N/A'}</span>
                            <span className="chunk-meta">
                              {c.text_length != null ? `${c.text_length} chars` : ''}
                            </span>
                          </div>
                          <div className="chunk-preview">{c.text_preview || ''}</div>
                        </div>
                      ))}
                    </div>
                  </>
                ) : (
                  <div className="empty">No RAG context.</div>
                )}

                <div className="separator" />

                <div className="section-title">Internet / On-demand</div>
                <div className="detail-row">
                  <span className="label">Used:</span> {internet?.used ? 'Yes' : 'No'}
                </div>
                <div className="detail-row">
                  <span className="label">Fetch (s):</span> {internet?.fetch_s ?? 0}
                </div>
                <div className="detail-row">
                  <span className="label">Discovery (s):</span> {internet?.discovery_s ?? 0}
                </div>
                <div className="detail-row">
                  <span className="label">Background refresh:</span> {internet?.background_refresh_started ? 'Started' : 'No'}
                </div>

                <div className="separator" />

                <div className="section-title">Messages Sent to Model</div>
                {selectedTrace.ollama?.messages?.length ? (
                  <div className="messages-list">
                    {selectedTrace.ollama.messages.map((m, idx) => (
                      <div key={`${m.role}-${idx}`} className="message-item">
                        <div className="message-head">
                          <span className="message-role">{m.role}</span>
                          <span className="message-meta">
                            {m.content_length_chars != null ? `${m.content_length_chars} chars` : ''}
                          </span>
                        </div>
                        <pre className="message-preview">{m.content_preview}</pre>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="empty">Messages not available.</div>
                )}

                <div className="separator" />

                <div className="section-title">Model Response</div>
                <div className="detail-row">
                  <span className="label">Latency:</span> {selectedTrace.response?.latency_ms ?? 'N/A'} ms
                </div>
                <pre className="response-preview">{selectedTrace.response?.content_preview}</pre>
              </div>
            )}
          </div>

          {mode === 'history' && historyTraces.length ? (
            <div className="card" style={{ marginTop: 12 }}>
              <div className="card-title">History Traces</div>
              <div className="history-list">
                {historyTraces.map((t, idx) => (
                  <button
                    key={t.meta.trace_id || idx}
                    type="button"
                    className={`history-item ${idx === selectedHistoryIndex ? 'active' : ''}`}
                    onClick={() => {
                      setSelectedHistoryIndex(idx);
                      setSelectedStepIndex(0);
                    }}
                  >
                    <div className="history-title">
                      {t.meta.trace_id || t.trace.trace_id || 'trace'}
                    </div>
                    <div className="history-sub">
                      {formatTs(t.meta.timestamp || t.trace.created_at)} • latency {t.meta.latency_ms ?? 'N/A'} ms
                    </div>
                    <div className="history-query">{t.meta.user_query ? String(t.meta.user_query).slice(0, 80) : ''}</div>
                  </button>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}

