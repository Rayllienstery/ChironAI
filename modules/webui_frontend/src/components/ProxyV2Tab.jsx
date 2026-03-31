import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  getModels,
  getProxyV2Settings,
  getProxyV2TraceCurrent,
  updateProxyV2Settings,
} from '../services/api';
import './ProxyV2Tab.css';
import './ProxyTraceTab.css';

const LIVE_POLL_MS = 750;
const STREAM_PREVIEW_MAX = 400;
const MAX_CAPTURED_TRACES = 200;
const MD_DIGEST_MSG_CHARS = 12000;

/** Longest run of consecutive "`" in s — used so Markdown fences are not broken by nested fences in JSON. */
function longestBacktickRun(s) {
  let max = 0;
  let run = 0;
  for (let i = 0; i < s.length; i += 1) {
    if (s[i] === '`') run += 1;
    else {
      if (run > max) max = run;
      run = 0;
    }
  }
  if (run > max) max = run;
  return max;
}

/** Opening/closing fence that safely wraps `inner` (e.g. JSON containing ``` in strings). */
function markdownCodeFence(inner, infoString) {
  const need = longestBacktickRun(inner) + 1;
  const n = Math.max(3, need);
  const tick = '`'.repeat(n);
  const lang = infoString != null && infoString !== '' ? infoString : '';
  return `${tick}${lang}\n${inner}\n${tick}`;
}

function flattenOpenAiMessageContent(content, maxLen) {
  const cap = maxLen ?? MD_DIGEST_MSG_CHARS;
  if (content == null) return '';
  if (typeof content === 'string') return content.length > cap ? `${content.slice(0, cap)}\n… [truncated]` : content;
  if (Array.isArray(content)) {
    const joined = content
      .map((p) => {
        if (p && typeof p === 'object' && typeof p.text === 'string') return p.text;
        if (typeof p === 'string') return p;
        return '';
      })
      .join('');
    return joined.length > cap ? `${joined.slice(0, cap)}\n… [truncated]` : joined;
  }
  const s = String(content);
  return s.length > cap ? `${s.slice(0, cap)}\n… [truncated]` : s;
}

function formatMessagesDigest(messages) {
  if (!Array.isArray(messages) || messages.length === 0) return '_No messages._\n';
  let md = '';
  messages.forEach((m, i) => {
    const role = m && typeof m.role === 'string' ? m.role : 'unknown';
    const text = flattenOpenAiMessageContent(m?.content, MD_DIGEST_MSG_CHARS);
    md += `**${i + 1}. ${role}**\n\n`;
    md += `${text}\n\n`;
  });
  return md;
}

function traceKey(trace) {
  if (!trace) return null;
  if (trace.trace_id) return String(trace.trace_id);
  if (trace.created_at) return `created:${trace.created_at}`;
  return null;
}

function downloadText(filename, text, mime) {
  const blob = new Blob([text], { type: mime || 'text/plain;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function formatTs(ts) {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return String(ts);
  }
}

function formatStreamLine(line) {
  if (line == null || line === '') return '';
  const s = String(line);
  if (s.startsWith('data: ') && s.includes('{')) {
    try {
      const jsonPart = s.slice(s.indexOf('{'));
      const parsed = JSON.parse(jsonPart);
      return JSON.stringify(parsed);
    } catch {
      return s;
    }
  }
  try {
    const o = JSON.parse(s);
    return JSON.stringify(o);
  } catch {
    return s;
  }
}

function ProxyV2TraceBody({ trace, updatedAt, status }) {
  const [rawOpen, setRawOpen] = useState(false);

  const phases = Array.isArray(trace?.phases) ? trace.phases : [];
  const streamEvents = Array.isArray(trace?.stream_events) ? trace.stream_events : [];
  const errors = Array.isArray(trace?.errors) ? trace.errors : [];
  const req = trace?.request && typeof trace.request === 'object' ? trace.request : {};
  const upstream = trace?.upstream && typeof trace.upstream === 'object' ? trace.upstream : {};

  const streamTail = useMemo(() => {
    if (streamEvents.length <= STREAM_PREVIEW_MAX) return streamEvents;
    return streamEvents.slice(-STREAM_PREVIEW_MAX);
  }, [streamEvents]);

  const streamHidden = streamEvents.length - streamTail.length;

  if (!trace) {
    return (
      <div className="proxy-v2-trace-empty">
        <p className="proxy-v2-trace-empty-title">No request yet</p>
        <p className="proxy-v2-trace-empty-hint">
          Send traffic to <code>http://&lt;host&gt;:8081</code> (e.g. <code>/v1/chat/completions</code> or{' '}
          <code>/api/chat</code>). The last request trace will appear here.
        </p>
        <p className="proxy-v2-trace-empty-meta">
          Polling: live · last update: {formatTs(updatedAt)}
        </p>
      </div>
    );
  }

  return (
    <div className="proxy-v2-trace-body">
      <div className="proxy-v2-card">
        <div className="proxy-v2-summary-grid">
          <div>
            <span className="proxy-v2-k">Trace ID</span>
            <span className="proxy-v2-v mono">{trace.trace_id || '—'}</span>
          </div>
          <div>
            <span className="proxy-v2-k">Created</span>
            <span className="proxy-v2-v">{formatTs(trace.created_at)}</span>
          </div>
          <div>
            <span className="proxy-v2-k">Status</span>
            <span className="proxy-v2-v">{status || '—'}</span>
          </div>
          <div>
            <span className="proxy-v2-k">Updated</span>
            <span className="proxy-v2-v">{formatTs(updatedAt)}</span>
          </div>
        </div>
      </div>

      {(req.path || req.method || Object.keys(req).length > 0) && (
        <section className="proxy-v2-section proxy-v2-card">
          <h4 className="proxy-v2-section-title">HTTP</h4>
          <dl className="proxy-v2-dl">
            {req.method ? (
              <>
                <dt>Method</dt>
                <dd className="mono">{String(req.method)}</dd>
              </>
            ) : null}
            {req.path ? (
              <>
                <dt>Path</dt>
                <dd className="mono">{String(req.path)}</dd>
              </>
            ) : null}
            {req.model_requested !== undefined && req.model_requested !== '' ? (
              <>
                <dt>Model (client)</dt>
                <dd className="mono">{String(req.model_requested)}</dd>
              </>
            ) : null}
            {req.model_resolved !== undefined && req.model_resolved !== '' ? (
              <>
                <dt>Model (resolved)</dt>
                <dd className="mono">{String(req.model_resolved)}</dd>
              </>
            ) : null}
          </dl>
          {req.openai_body != null && typeof req.openai_body === 'object' ? (
            <details className="proxy-v2-details">
              <summary>Client body (OpenAI-shaped JSON)</summary>
              <pre className="proxy-v2-code">{JSON.stringify(req.openai_body, null, 2)}</pre>
            </details>
          ) : null}
        </section>
      )}

      {Object.keys(upstream).length > 0 && (
        <section className="proxy-v2-section proxy-v2-card">
          <h4 className="proxy-v2-section-title">Upstream (Ollama)</h4>
          <dl className="proxy-v2-dl">
            {upstream.url ? (
              <>
                <dt>URL</dt>
                <dd className="mono break-all">{String(upstream.url)}</dd>
              </>
            ) : null}
            {upstream.segment ? (
              <>
                <dt>Segment</dt>
                <dd className="mono">{String(upstream.segment)}</dd>
              </>
            ) : null}
            {upstream.status != null ? (
              <>
                <dt>HTTP status</dt>
                <dd>{String(upstream.status)}</dd>
              </>
            ) : null}
          </dl>
          {upstream.body != null && (
            <details className="proxy-v2-details">
              <summary>Request body (JSON)</summary>
              <pre className="proxy-v2-code">{JSON.stringify(upstream.body, null, 2)}</pre>
            </details>
          )}
          {upstream.body_summary != null && upstream.body == null && (
            <pre className="proxy-v2-code">{JSON.stringify(upstream.body_summary, null, 2)}</pre>
          )}
        </section>
      )}

      {phases.length > 0 && (
        <section className="proxy-v2-section proxy-v2-card">
          <h4 className="proxy-v2-section-title">Phases ({phases.length})</h4>
          <ol className="proxy-v2-phases">
            {phases.map((p, i) => (
              <li key={i} className="proxy-v2-phase">
                <span className="proxy-v2-phase-name">{p.name || 'phase'}</span>
                <pre className="proxy-v2-phase-json">{JSON.stringify(p, null, 2)}</pre>
              </li>
            ))}
          </ol>
        </section>
      )}

      {streamTail.length > 0 && (
        <section className="proxy-v2-section proxy-v2-card">
          <h4 className="proxy-v2-section-title">
            Stream / NDJSON lines
            {trace.stream_truncated ? (
              <span className="proxy-v2-badge-warn"> truncated (ring buffer)</span>
            ) : null}
            {streamHidden > 0 ? (
              <span className="proxy-v2-badge-muted"> showing last {streamTail.length}</span>
            ) : null}
          </h4>
          <div className="proxy-v2-stream-scroll">
            {streamTail.map((line, i) => (
              <div key={`${i}-${line.slice(0, 40)}`} className="proxy-v2-stream-line mono">
                {formatStreamLine(line)}
              </div>
            ))}
          </div>
        </section>
      )}

      {errors.length > 0 && (
        <section className="proxy-v2-section proxy-v2-card proxy-v2-card-error">
          <h4 className="proxy-v2-section-title">Errors</h4>
          {errors.map((err, i) => (
            <div key={i} className="proxy-v2-error-block">
              <p className="proxy-v2-error-msg">{err.message || String(err)}</p>
              {err.traceback ? <pre className="proxy-v2-code proxy-v2-tb">{err.traceback}</pre> : null}
            </div>
          ))}
        </section>
      )}

      <section className="proxy-v2-section">
        <button type="button" className="proxy-v2-raw-toggle btn" onClick={() => setRawOpen((o) => !o)}>
          {rawOpen ? '▼ Hide raw JSON' : '▶ Show raw JSON'}
        </button>
        {rawOpen ? (
          <pre className="proxy-v2-code proxy-v2-raw-json">{JSON.stringify(trace, null, 2)}</pre>
        ) : null}
      </section>
    </div>
  );
}

export default function ProxyV2Tab() {
  const [models, setModels] = useState([]);
  const [model, setModel] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [live, setLive] = useState({ trace: null, updated_at: null, status: null });
  const [captures, setCaptures] = useState([]);
  const [selectedIndex, setSelectedIndex] = useState(0);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [mList, st] = await Promise.all([getModels(), getProxyV2Settings()]);
        if (cancelled) return;
        setModels(Array.isArray(mList) ? mList : []);
        setModel((st && st.model) ? String(st.model) : '');
      } catch (e) {
        console.error(e);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    const poll = async () => {
      try {
        const payload = await getProxyV2TraceCurrent();
        if (cancelled) return;
        const next = {
          trace: payload.trace ?? null,
          updated_at: payload.updated_at ?? null,
          status: payload.status ?? null,
        };
        setLive(next);
        if (next.trace) {
          const key = traceKey(next.trace);
          setCaptures((prev) => {
            const prevLen = prev.length;
            const last = prevLen ? prev[prevLen - 1] : null;
            const lastKey = last && traceKey(last.trace);

            let nextArr;
            if (!last || key == null || lastKey == null || key !== lastKey) {
              nextArr = [...prev, next];
            } else {
              nextArr = [...prev.slice(0, prevLen - 1), next];
            }

            if (nextArr.length > MAX_CAPTURED_TRACES) {
              const overflow = nextArr.length - MAX_CAPTURED_TRACES;
              nextArr = nextArr.slice(overflow);
            }
            return nextArr;
          });
        }
      } catch {
        /* keep UI alive */
      }
    };
    poll();
    const id = setInterval(poll, LIVE_POLL_MS);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, []);

  const modelIds = useMemo(() => models.map((x) => x.id).filter(Boolean), [models]);
  const selectValue = modelIds.includes((model || '').trim()) ? model : '';

  const selectedCapture = captures.length ? captures[Math.min(selectedIndex, captures.length - 1)] : null;
  const selectedTrace = selectedCapture?.trace || null;
  const selectedStatus = selectedCapture?.status || live.status || null;
  const selectedUpdatedAt = selectedCapture?.updated_at || live.updated_at || null;

  const handleResetCaptures = () => {
    setCaptures([]);
    setSelectedIndex(0);
  };

  const handleSelectCapture = (idx) => {
    setSelectedIndex(idx);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      await updateProxyV2Settings({ model: model || '' });
      window.alert('Proxy V2 model saved.');
    } catch (e) {
      console.error(e);
      window.alert('Failed to save');
    } finally {
      setSaving(false);
    }
  };

  const exportJson = useCallback(() => {
    const payload = {
      exported_at: new Date().toISOString(),
      traces: captures.map((c) => ({
        trace: c.trace,
        updated_at: c.updated_at,
        status: c.status,
      })),
    };
    const body = JSON.stringify(payload, null, 2);
    const stamp = (selectedUpdatedAt || 'traces').replace(/[:.]/g, '-');
    downloadText(`proxy-v2-traces-${stamp}.json`, body, 'application/json');
  }, [captures, selectedUpdatedAt]);

  const exportMd = useCallback(() => {
    let md = '# Proxy V2 traces export\n\n';
    md += `- exported_at: ${new Date().toISOString()}\n`;
    md += `- count: ${captures.length}\n\n`;
    md +=
      '_Tip: for parsers and LLMs that need the full structured payload, prefer **Export JSON**. ';
    md +=
      'This Markdown adds a **message digest** (readable tasks) and uses extended code fences so triple-backtick snippets inside JSON strings do not terminate a fence early._\n\n';

    if (!captures.length) {
      md += '_No traces captured yet._\n';
    } else {
      captures.forEach((c, idx) => {
        const t = c.trace || {};
        const reqObj = t.request && typeof t.request === 'object' ? t.request : {};
        const openaiBody = reqObj.openai_body;
        const up = t.upstream && typeof t.upstream === 'object' ? t.upstream : {};
        const upBody = up.body && typeof up.body === 'object' ? up.body : null;

        md += `## Trace ${idx + 1}\n\n`;
        md += `- trace_id: \`${t.trace_id || '—'}\`\n`;
        md += `- created_at: ${t.created_at || '—'}\n`;
        md += `- updated_at: ${c.updated_at || '—'}\n`;
        md += `- status: ${c.status || '—'}\n`;
        md += `- path: \`${reqObj.path || '—'}\`\n\n`;

        md += '### Message digest (for analysis)\n\n';
        md += '#### OpenAI-shaped `messages` (client)\n\n';
        if (openaiBody && Array.isArray(openaiBody.messages)) {
          md += formatMessagesDigest(openaiBody.messages);
        } else {
          md += '_No `openai_body.messages` on this trace._\n\n';
        }
        md += '#### Ollama chat `messages` (sent to `/api/chat`)\n\n';
        if (upBody && Array.isArray(upBody.messages)) {
          md += formatMessagesDigest(upBody.messages);
        } else {
          md += '_No `upstream.body.messages` (e.g. legacy completions or forward-only route)._\n\n';
        }

        if (t.request && Object.keys(t.request).length) {
          md += '### request (full JSON)\n\n';
          md += `${markdownCodeFence(JSON.stringify(t.request, null, 2), 'json')}\n`;
        }
        if (t.upstream && Object.keys(t.upstream).length) {
          md += '\n### upstream (Ollama, full JSON)\n\n';
          md += `${markdownCodeFence(JSON.stringify(t.upstream, null, 2), 'json')}\n`;
        }
        if (Array.isArray(t.phases) && t.phases.length) {
          md += '\n### phases\n\n';
          t.phases.forEach((p, i) => {
            md += `${i + 1}. **${p.name || 'phase'}** — \`${JSON.stringify(p)}\`\n`;
          });
        }
        if (t.errors && t.errors.length) {
          md += '\n### errors\n\n';
          md += `${markdownCodeFence(JSON.stringify(t.errors, null, 2), '')}\n`;
        }
        md += '\n';
      });
    }

    const stamp = (selectedUpdatedAt || 'traces').replace(/[:.]/g, '-');
    downloadText(`proxy-v2-traces-${stamp}.md`, md, 'text/markdown');
  }, [captures, selectedUpdatedAt]);

  if (loading) {
    return <div className="proxy-v2-tab loading">Loading…</div>;
  }

  return (
    <div className="proxy-v2-tab settings-tab">
      <div className="proxy-v2-top">
        <div className="proxy-v2-header proxy-trace-header">
          <h2>Proxy V2</h2>
          <div className="proxy-v2-header-right">
            <button type="button" className="btn proxy-trace-export-btn" onClick={exportJson}>
              Export JSON
            </button>
            <button type="button" className="btn proxy-trace-export-btn" onClick={exportMd}>
              Export Markdown
            </button>
          </div>
        </div>

        <div className="settings-section proxy-v2-intro">
          <p>
            Ollama passthrough on port <strong>8081</strong> (see <code>config/server.yaml</code> /
            <code>PASS_PROXY_V2_PORT</code>). Point your IDE at{' '}
            <code>http://&lt;this-host&gt;:8081/v1</code> or native <code>/api/chat</code>. No RAG in this
            proxy — full Ollama semantics plus live trace below.
          </p>
        </div>

        <div className="settings-form model-settings proxy-v2-model">
          <label className="settings-label" htmlFor="proxy-v2-model-select">
            Pinned Ollama model (optional)
          </label>
          <select
            id="proxy-v2-model-select"
            className="settings-select"
            value={selectValue}
            onChange={(e) => setModel(e.target.value)}
          >
            <option value="">— Use client model —</option>
            {modelIds.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </select>
          <button type="button" className="btn primary" disabled={saving} onClick={handleSave}>
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>

      <div className="proxy-v2-trace-panel">
        <div className="proxy-v2-trace-toolbar">
          <h3>Live trace</h3>
          <p className="proxy-v2-trace-meta">
            <span>status: {selectedStatus || '—'}</span>
            <span>updated: {formatTs(selectedUpdatedAt)}</span>
            {selectedTrace?.stream_truncated ? (
              <span className="proxy-v2-trunc">stream truncated in buffer</span>
            ) : null}
          </p>
          <div className="proxy-v2-trace-tabs-row">
            <div className="proxy-v2-trace-tabs" role="tablist" aria-label="Proxy V2 traces">
              {captures.map((c, idx) => {
                const t = c.trace || {};
                const id = t.trace_id || `trace-${idx + 1}`;
                const created = t.created_at || c.updated_at || '';
                const labelId = `proxy-v2-trace-tab-${idx}`;
                const isSelected = idx === selectedIndex;
                return (
                  <button
                    key={labelId}
                    type="button"
                    role="tab"
                    aria-selected={isSelected}
                    className={`proxy-v2-trace-tab-btn${isSelected ? ' is-active' : ''}`}
                    id={labelId}
                    onClick={() => handleSelectCapture(idx)}
                  >
                    <span className="proxy-v2-trace-tab-id">{String(id).slice(0, 16)}</span>
                    <span className="proxy-v2-trace-tab-meta">{formatTs(created)}</span>
                  </button>
                );
              })}
              {!captures.length ? <span className="proxy-v2-trace-tabs-empty">No tracks yet</span> : null}
            </div>
            <button
              type="button"
              className="btn proxy-v2-trace-reset-btn"
              onClick={handleResetCaptures}
              disabled={!captures.length}
            >
              Reset tracks
            </button>
          </div>
        </div>
        <ProxyV2TraceBody trace={selectedTrace} updatedAt={selectedUpdatedAt} status={selectedStatus} />
      </div>
    </div>
  );
}
