import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  getProxyLogs,
  getProxyTraceCurrent,
  getSettings,
  updateSettings,
} from '../services/api';
import '../styles/components/ProxyTraceTab.css';

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

function traceModelFields(trace) {
  if (!trace) {
    return { headerShort: 'N/A', ollama: null, requested: null, actual: null };
  }
  const req = trace.request || {};
  const oll = trace.ollama || {};
  const ollama = oll.model != null && oll.model !== '' ? String(oll.model) : null;
  const requested =
    req.requested_model != null && req.requested_model !== '' ? String(req.requested_model) : null;
  const actual = req.actual_model != null && req.actual_model !== '' ? String(req.actual_model) : null;
  const headerShort = ollama || actual || requested || 'N/A';
  return { headerShort, ollama, requested, actual };
}

function mdFencedBlock(text) {
  const body = text == null ? '' : String(text);
  let fence = '```';
  while (body.includes(fence)) {
    fence += '`';
  }
  return `${fence}\n${body}\n${fence}`;
}

/** @param {object} params */
export function buildProxyTraceMarkdown({
  mode,
  livePayload,
  selectedTrace,
  historyMeta,
  graph,
  modelMaxContextTokens,
  selectedStepIndex,
}) {
  const lines = [];
  const nowIso = new Date().toISOString();
  lines.push('# Proxy Trace Export', '');
  lines.push(`**Generated:** ${nowIso}`, `**Mode:** ${mode}`, '');

  if (mode === 'live') {
    lines.push('## Summary (Live)', '');
    lines.push(`- **Status:** ${livePayload?.status ?? 'N/A'}`);
    lines.push(`- **Updated:** ${formatTs(livePayload?.updated_at)}`, '');
  }

  if (mode === 'history' && historyMeta) {
    lines.push('## History entry', '');
    lines.push(
      `- **Trace ID:** ${historyMeta.trace_id ?? selectedTrace?.trace_id ?? 'N/A'}`,
    );
    lines.push(`- **Log timestamp:** ${formatTs(historyMeta.timestamp)}`);
    lines.push(`- **Latency (ms):** ${historyMeta.latency_ms ?? 'N/A'}`);
    if (historyMeta.user_query) {
      lines.push('- **User query:**', mdFencedBlock(String(historyMeta.user_query)));
    }
    lines.push('');
  }

  if (!selectedTrace) {
    lines.push('*(No trace data.)*', '');
    return lines.join('\n');
  }

  const { ollama, requested, actual } = traceModelFields(selectedTrace);
  lines.push('## Models', '');
  lines.push(`- **Model (Ollama):** ${ollama ?? 'N/A'}`);
  lines.push(`- **Model (resolved / request):** ${actual ?? 'N/A'}`);
  lines.push(`- **Requested model:** ${requested ?? 'N/A'}`, '');

  lines.push('## Context usage', '');
  lines.push(
    `- **RAG budget used:** ${graph.ragUsedPct == null ? 'N/A' : `${graph.ragUsedPct.toFixed(1)}%`}`,
  );
  lines.push(
    `- **Model window used:** ${graph.modelPct == null ? 'N/A' : `${graph.modelPct.toFixed(1)}%`}`,
  );
  lines.push(`- **Total tokens (est):** ${graph.totalTokens ?? 'N/A'}`);
  lines.push(`- **Model max context tokens (setting):** ${modelMaxContextTokens || 'N/A'}`, '');

  const steps = selectedTrace.steps || [];
  lines.push('## Steps', '');
  if (steps.length) {
    steps.forEach((s, idx) => {
      const mark = idx === selectedStepIndex ? ' (selected)' : '';
      lines.push(
        `${idx + 1}. **${s.name || 'step'}**${mark} — ${s.duration_ms != null ? `${s.duration_ms} ms` : ''}`,
      );
    });
  } else {
    lines.push('*(No steps.)*');
  }
  lines.push('');

  const sel = steps[selectedStepIndex] || null;
  lines.push('## Selected step', '');
  if (sel) {
    lines.push(`- **Name:** ${sel.name}`);
    lines.push(`- **Duration (ms):** ${sel.duration_ms ?? 'N/A'}`);
    lines.push(`- **Tokens in (est):** ${sel.tokens_in_est ?? 'N/A'}`);
    lines.push(`- **Tokens out (est):** ${sel.tokens_out_est ?? 0}`);
  } else {
    lines.push('*(None.)*');
  }
  lines.push('');

  lines.push('## Trace', '');
  lines.push(`- **Trace ID:** ${selectedTrace.trace_id ?? 'N/A'}`);
  lines.push(`- **Created:** ${formatTs(selectedTrace.created_at)}`, '');

  lines.push('## RAG Context', '');
  const ragCtx = selectedTrace.rag?.context;
  if (ragCtx) {
    lines.push(`- **Context chars used:** ${ragCtx.context_chars_used}`);
    lines.push(`- **Context budget chars:** ${ragCtx.context_budget_chars}`);
    lines.push(`- **Chunks:** ${ragCtx.chunks?.length ?? 0}`, '');
    const chunks = ragCtx.chunks || [];
    chunks.forEach((c, i) => {
      lines.push(`### Chunk ${i + 1}: ${c.label || 'N/A'}`, '');
      if (c.text_length != null) {
        lines.push(`_${c.text_length} chars_`, '');
      }
      lines.push(mdFencedBlock(c.text_preview || ''), '');
    });
  } else {
    lines.push('*(No RAG context.)*', '');
  }

  const internet = selectedTrace.internet || {};
  lines.push('## Internet / On-demand', '');
  lines.push(`- **Used:** ${internet.used ? 'Yes' : 'No'}`);
  lines.push(`- **Fetch (s):** ${internet.fetch_s ?? 0}`);
  lines.push(`- **Discovery (s):** ${internet.discovery_s ?? 0}`);
  lines.push(
    `- **Background refresh:** ${internet.background_refresh_started ? 'Started' : 'No'}`,
    '',
  );

  lines.push('## Messages sent to model', '');
  const msgs = selectedTrace.ollama?.messages;
  if (msgs?.length) {
    msgs.forEach((m, idx) => {
      lines.push(`### ${m.role || 'message'} (${idx + 1})`, '');
      if (m.content_length_chars != null) {
        lines.push(`_${m.content_length_chars} chars_`, '');
      }
      lines.push(mdFencedBlock(m.content_full || m.content_preview || ''), '');
    });
  } else {
    lines.push('*(Messages not available.)*', '');
  }

  lines.push('## Model response', '');
  lines.push(`- **Latency (ms):** ${selectedTrace.response?.latency_ms ?? 'N/A'}`, '');
  lines.push(mdFencedBlock(selectedTrace.response?.content_preview || ''), '');

  return lines.join('\n');
}

function ollamaMessageFullText(m) {
  if (!m) return '';
  if (m.content_full != null && m.content_full !== '') return String(m.content_full);
  return m.content_preview != null ? String(m.content_preview) : '';
}

/** True when the trace payload includes full message body (not only the short preview). */
function ollamaMessageHasStoredFullText(m) {
  return m != null && m.content_full != null && String(m.content_full).length > 0;
}

function downloadMarkdown(filename, text) {
  const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
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
  const [messageModal, setMessageModal] = useState(null);

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

  useEffect(() => {
    if (!messageModal) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setMessageModal(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [messageModal]);

  const graph = useMemo(() => {
    const rag = selectedTrace?.rag?.context;
    const ragUsedPct = rag?.context_budget_chars
      ? toPct(rag?.context_chars_used || 0, rag?.context_budget_chars || 0)
      : null;

    const totalTokens = selectedTrace?.ollama?.tokens_estimates?.total_tokens_estimated;
    const modelPct = modelMaxContextTokens > 0 ? toPct(totalTokens || 0, modelMaxContextTokens) : null;
    return { ragUsedPct, modelPct, totalTokens };
  }, [selectedTrace, modelMaxContextTokens]);

  const historyMeta = useMemo(() => {
    if (mode !== 'history' || selectedHistoryIndex == null) return null;
    return historyTraces[selectedHistoryIndex]?.meta ?? null;
  }, [mode, selectedHistoryIndex, historyTraces]);

  const modelInfo = useMemo(() => traceModelFields(selectedTrace), [selectedTrace]);

  const selectedStep = steps[selectedStepIndex] || null;

  const ragChunks = selectedTrace?.rag?.context?.chunks || [];
  const internet = selectedTrace?.internet || {};

  const exportFilename = () => {
    const id = (selectedTrace && selectedTrace.trace_id) || 'unknown';
    const stamp = new Date().toISOString().slice(0, 19).replace(/:/g, '-');
    return `proxy-trace-${mode}-${id}-${stamp}.md`;
  };

  const handleExportMarkdown = () => {
    if (!selectedTrace) return;
    const md = buildProxyTraceMarkdown({
      mode,
      livePayload,
      selectedTrace,
      historyMeta,
      graph,
      modelMaxContextTokens,
      selectedStepIndex,
    });
    downloadMarkdown(exportFilename(), md);
  };

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

        <div className="proxy-trace-header-right">
          {mode === 'live' ? (
            <div className="live-meta">
              <div>
                <span className="label">Status:</span> {livePayload?.status || 'N/A'}
              </div>
              <div>
                <span className="label">Updated:</span> {formatTs(livePayload?.updated_at)}
              </div>
              <div>
                <span className="label">Model:</span> {modelInfo.headerShort}
              </div>
            </div>
          ) : (
            <div className="live-meta">
              <div>
                <span className="label">Loaded:</span> {historyTraces.length} traces (last {HISTORY_LIMIT})
              </div>
              {selectedTrace ? (
                <div>
                  <span className="label">Model:</span> {modelInfo.headerShort}
                </div>
              ) : null}
            </div>
          )}
          <button
            type="button"
            className="btn proxy-trace-export-btn"
            disabled={!selectedTrace}
            onClick={handleExportMarkdown}
          >
            Export
          </button>
        </div>
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
                <div className="detail-row">
                  <span className="label">Model (Ollama):</span> {modelInfo.ollama ?? 'N/A'}
                </div>
                <div className="detail-row">
                  <span className="label">Model (resolved):</span> {modelInfo.actual ?? 'N/A'}
                </div>
                <div className="detail-row">
                  <span className="label">Requested model:</span> {modelInfo.requested ?? 'N/A'}
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
                          <div className="message-head-actions">
                            <span className="message-meta">
                              {m.content_length_chars != null ? `${m.content_length_chars} chars` : ''}
                            </span>
                            <button
                              type="button"
                              className="message-view-full-btn"
                              onClick={() =>
                                setMessageModal({
                                  title: `${m.role || 'message'} (${idx + 1})`,
                                  body: ollamaMessageFullText(m),
                                  previewOnly: !ollamaMessageHasStoredFullText(m),
                                })
                              }
                            >
                              View Full
                            </button>
                          </div>
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

      {messageModal ? (
        <div
          className="proxy-trace-modal-overlay"
          role="presentation"
          onClick={() => setMessageModal(null)}
        >
          <div
            className="proxy-trace-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="proxy-trace-modal-title"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="proxy-trace-modal-header">
              <h2 id="proxy-trace-modal-title" className="proxy-trace-modal-title">
                {messageModal.title}
              </h2>
              <button
                type="button"
                className="proxy-trace-modal-close"
                onClick={() => setMessageModal(null)}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            {messageModal.previewOnly ? (
              <div className="proxy-trace-modal-note" role="status">
                Showing the short preview only. Full bodies are stored once the proxy API persists{' '}
                <code className="proxy-trace-modal-note-code">content_full</code> on each message — restart the
                server so it runs the latest backend code, then send a new chat request. Older History entries
                may remain preview-only.
              </div>
            ) : null}
            <pre className="proxy-trace-modal-body">{messageModal.body}</pre>
          </div>
        </div>
      ) : null}
    </div>
  );
}

