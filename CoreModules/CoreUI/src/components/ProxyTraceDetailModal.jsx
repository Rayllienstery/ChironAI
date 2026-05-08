import { useEffect, useMemo, useState } from 'react';
import { summarizeAgentTraceMeta } from '../utils/agentTraceSummary';
import AgentTraceSummaryCards from './AgentTraceSummaryCards';
import Card from './Card';
import '../styles/components/DashboardTab.css';

function readMetadata(log) {
  if (!log || !log.metadata) return {};
  if (typeof log.metadata === 'string') {
    try {
      return JSON.parse(log.metadata);
    } catch {
      return {};
    }
  }
  return log.metadata;
}

function isAgentTraceDetailLog(log, meta) {
  if (!log) return false;
  if (meta.trace_id != null && String(meta.trace_id).trim() !== '') {
    if (meta.request != null && typeof meta.request === 'object') return true;
    if (Array.isArray(meta.steps)) return true;
  }
  return false;
}

function AgentTraceStepBlock({ step, index }) {
  if (!step || typeof step !== 'object') return null;
  const kind = step.kind;
  const label =
    kind ||
    (step.name != null && String(step.name).trim() !== '' ? String(step.name) : 'unknown');
  return (
    <details className="dashboard-trace-item coreui-section-block">
      <summary>
        Step {index + 1}: <code>{label}</code>
        {step.step != null ? ` (agent step ${step.step})` : ''}
        {step.ok === false ? ' · failed' : ''}
      </summary>
      <div className="dashboard-card-muted coreui-stack-sm">
        {kind === 'model_call' && (
          <>
            {step.model != null && (
              <p>
                <strong>Model:</strong> <code>{step.model}</code>
              </p>
            )}
            {(step.prompt_tokens_est != null || step.completion_tokens_est != null) && (
              <p className="coreui-text-muted-sm">
                Token est.: prompt {step.prompt_tokens_est ?? '—'} · completion {step.completion_tokens_est ?? '—'}
              </p>
            )}
            {step.finish_reason != null && (
              <p>
                <strong>Finish:</strong> <code>{step.finish_reason}</code>
              </p>
            )}
            {step.thinking_raw != null && String(step.thinking_raw).trim() !== '' && (
              <div className="coreui-stack-xs">
                <strong>Thinking (raw)</strong>
                <pre className="coreui-mono-block">
                  {step.thinking_raw}
                </pre>
              </div>
            )}
            {step.assistant_content_raw != null && String(step.assistant_content_raw).trim() !== '' && (
              <div className="coreui-stack-xs">
                <strong>Assistant content (raw)</strong>
                <pre className="coreui-mono-block">
                  {step.assistant_content_raw}
                </pre>
              </div>
            )}
            {step.assistant_visible != null && String(step.assistant_visible).trim() !== '' && (
              <div className="coreui-stack-xs">
                <strong>Assistant (merged visible)</strong>
                <pre className="coreui-mono-block">
                  {step.assistant_visible}
                </pre>
              </div>
            )}
            {Array.isArray(step.tool_calls) && step.tool_calls.length > 0 && (
              <div className="coreui-stack-xs">
                <strong>Tool calls</strong>
                <pre className="coreui-mono-block">
                  {JSON.stringify(step.tool_calls, null, 2)}
                </pre>
              </div>
            )}
            {step.error != null && <p className="dashboard-card-error">{String(step.error)}</p>}
          </>
        )}
        {kind === 'tool_rag' && (
          <>
            <p>
              <strong>Query:</strong> {step.query || '—'}
            </p>
            <p>
              Chunks: {step.chunks ?? '—'} · max_score: {step.max_score ?? '—'} · context_chars: {step.context_chars ?? '—'}
            </p>
            {step.error != null && <p className="dashboard-card-error">{String(step.error)}</p>}
            {Array.isArray(step.chunks_info) && step.chunks_info.length > 0 && (
              <pre className="coreui-mono-block">
                {JSON.stringify(step.chunks_info, null, 2)}
              </pre>
            )}
          </>
        )}
        {kind === 'tool_skill' && (
          <>
            <p>
              <strong>Invocation:</strong> {step.invocation || '—'}
            </p>
            {step.skill_id != null && String(step.skill_id).trim() !== '' && (
              <p>
                <strong>skill_id:</strong> <code>{step.skill_id}</code>
              </p>
            )}
            <p>
              context_chars: {step.context_chars ?? '—'} · duration_ms: {step.duration_ms ?? '—'}
            </p>
            {step.error != null && <p className="dashboard-card-error">{String(step.error)}</p>}
          </>
        )}
        {kind === 'tool_pass_through' && (
          <>
            <p>
              <strong>Tools returned to IDE:</strong>{' '}
              {Array.isArray(step.names) && step.names.length > 0 ? step.names.join(', ') : '—'}
            </p>
            <details className="dashboard-trace-item coreui-section-block">
              <summary>Raw step JSON</summary>
              <pre className="coreui-mono-block">{JSON.stringify(step, null, 2)}</pre>
            </details>
          </>
        )}
        {(kind === 'tool_unhandled' || kind === 'config_error') && (
          <pre className="coreui-mono-block">{JSON.stringify(step, null, 2)}</pre>
        )}
        {!kind && step.name != null && String(step.name).trim() !== '' && (
          <>
            <p>
              <strong>Duration:</strong> {step.duration_ms != null ? `${step.duration_ms} ms` : '—'}
            </p>
            {(step.tokens_in_est != null || step.tokens_out_est != null) && (
              <p className="coreui-text-muted-sm">
                Token est.: in {step.tokens_in_est ?? '—'} · out {step.tokens_out_est ?? '—'}
              </p>
            )}
            <pre className="coreui-mono-block">{JSON.stringify(step, null, 2)}</pre>
          </>
        )}
        {kind !== 'model_call' &&
          kind !== 'tool_rag' &&
          kind !== 'tool_skill' &&
          kind !== 'tool_pass_through' &&
          kind !== 'tool_unhandled' &&
          kind !== 'config_error' &&
          !(step.name != null && String(step.name).trim() !== '' && !kind) && (
            <pre className="coreui-mono-block">{JSON.stringify(step, null, 2)}</pre>
          )}
      </div>
    </details>
  );
}

function ProxyRequestStructuredBody({ log, meta }) {
  const isAc = Boolean(meta.is_autocomplete);
  const backend = meta.proxy_backend;
  const ragContext = meta.rag_context || {};
  const chunksCount = ragContext.chunks_count || 0;
  const maxScore = ragContext.max_score;
  const chunksInfo = Array.isArray(ragContext.chunks_info) ? ragContext.chunks_info : [];

  const pipelineLabel =
    backend === 'rag_fusion' ? 'RAG Fusion' : backend ? String(backend) : '—';

  return (
    <div className="proxy-trace-detail-body coreui-stack-md">
      <Card className="coreui-p-md">
        <p className="coreui-text-muted-sm" style={{ margin: 0 }}>
          <strong>Pipeline:</strong> {pipelineLabel}
          {isAc ? ' · Autocomplete' : ''}
        </p>
      </Card>

      <Card className="coreui-p-md coreui-stack-xs">
        <strong>User query</strong>
        <div className="dashboard-card-muted coreui-text-break">
          {meta.user_query || '—'}
        </div>
      </Card>

      <Card className="coreui-p-md coreui-stack-xs">
        <strong>Response preview</strong>
        <div className="dashboard-card-muted coreui-text-break">
          {meta.response_preview || '—'}
        </div>
      </Card>

      <div className="coreui-inline-cluster coreui-gap-sm">
        <div className="coreui-status-pill">
          <strong>Model:</strong> {meta.model || 'N/A'}
        </div>
        <div className="coreui-status-pill">
          <strong>Latency:</strong> {meta.latency_ms != null ? `${meta.latency_ms} ms` : '—'}
        </div>
        <div className="coreui-status-pill">
          <strong>Prompt tok.:</strong> {meta.prompt_tokens ?? '—'}
        </div>
        <div className="coreui-status-pill">
          <strong>Completion tok.:</strong> {meta.completion_tokens ?? '—'}
        </div>
        <div className="coreui-status-pill">
          <strong>Total tok.:</strong> {meta.total_tokens ?? '—'}
        </div>
      </div>

      {meta.rag_steps && (
        <Card className="coreui-p-md coreui-stack-xs">
          <strong>RAG steps (time)</strong>
          <p className="coreui-text-muted-sm" style={{ margin: 0 }}>
            embed {Number(meta.rag_steps.embed_s ?? 0).toFixed(2)}s · search {Number(meta.rag_steps.search_s ?? 0).toFixed(2)}s ·
            rerank {Number(meta.rag_steps.rerank_s ?? 0).toFixed(2)}s
            {meta.rag_steps.total_rag_s != null && <> (total RAG {Number(meta.rag_steps.total_rag_s).toFixed(2)}s)</>}
          </p>
        </Card>
      )}

      {chunksCount > 0 && (
        <Card className="coreui-p-md coreui-stack-xs">
          <strong>RAG context</strong>
          <p className="coreui-text-muted-sm" style={{ margin: 0 }}>
            Chunks: {chunksCount} · Max score: {typeof maxScore === 'number' ? maxScore.toFixed(3) : maxScore || 'N/A'} · Context
            length: {ragContext.context_length || 0} chars
          </p>
          {chunksInfo.length > 0 && (
            <ul className="coreui-list-tight">
              {chunksInfo.slice(0, 12).map((chunk, idx) => (
                <li key={idx}>
                  <strong>#{idx + 1}</strong> {chunk?.doc_type || 'N/A'}
                  {typeof chunk?.score === 'number' ? ` · score ${chunk.score.toFixed(4)}` : ''}
                  {chunk?.url ? (
                    <div className="coreui-text-break-all">{chunk.url}</div>
                  ) : null}
                </li>
              ))}
              {chunksInfo.length > 12 ? <li>… +{chunksInfo.length - 12} more</li> : null}
            </ul>
          )}
        </Card>
      )}

      {log?.timestamp && (
        <Card className="coreui-p-md">
          <p className="coreui-text-muted-sm" style={{ margin: 0 }}>
            Log time: {log.timestamp}
          </p>
        </Card>
      )}
    </div>
  );
}

/**
 * Full-screen trace / request detail.
 */
export default function ProxyTraceDetailModal({ log, isOpen, onClose }) {
  const [showRaw, setShowRaw] = useState(false);

  useEffect(() => {
    if (!isOpen) setShowRaw(false);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [isOpen, onClose]);

  const meta = useMemo(() => (log ? readMetadata(log) : null), [log]);
  const traceSummary = useMemo(() => summarizeAgentTraceMeta(meta), [meta]);
  const agentTraceStyle = log && meta ? isAgentTraceDetailLog(log, meta) : false;
  const titleId = 'proxy-trace-detail-modal-title';

  const handleExportJson = () => {
    const data = meta || log;
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    const timestamp = log.timestamp ? log.timestamp.replace(/[: ]/g, '-') : Date.now();
    a.download = `proxy-request-${log.id || timestamp}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  if (!isOpen || !log) return null;

  return (
    <div className="proxy-journal-modal-overlay" role="presentation" onClick={onClose}>
      <div
        className="proxy-journal-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="proxy-journal-modal-header">
          <div className="proxy-journal-modal-title-block">
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
              <h2 id={titleId} style={{ margin: 0 }}>{agentTraceStyle ? 'Trace detail' : 'Request detail'}</h2>
              <button
                type="button"
                className="proxy-journal-modal-export-btn"
                onClick={handleExportJson}
                title="Export as JSON"
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
              </button>
            </div>
            <p className="proxy-journal-modal-meta" style={{ marginTop: '4px' }}>{log.timestamp}</p>
            {meta?.trace_id != null && String(meta.trace_id).trim() !== '' && (
              <p className="proxy-journal-modal-meta">
                <code>{String(meta.trace_id)}</code>
              </p>
            )}
          </div>
          <div className="proxy-journal-modal-header-actions">
            <label className="coreui-checkbox dashboard-card-muted">
              <input type="checkbox" checked={showRaw} onChange={(e) => setShowRaw(e.target.checked)} />
              Raw JSON
            </label>
            <button type="button" className="proxy-journal-modal-close" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <div className="proxy-journal-modal-body">
          {showRaw && (
            <pre className="coreui-mono-block">
              {JSON.stringify(meta || log, null, 2)}
            </pre>
          )}
          {!showRaw && agentTraceStyle && meta && (
            <>
              <AgentTraceSummaryCards summary={traceSummary} />
              {meta.request != null && (
                <details className="dashboard-trace-item">
                  <summary>
                    Request snapshot
                    {Array.isArray(meta.request.messages) ? ` · ${meta.request.messages.length} messages` : ''}
                    {' · '}
                    {Array.isArray(meta.request.client_tool_names)
                      ? `${meta.request.client_tool_names.length} client tools`
                      : '0 client tools'}
                    {meta.request.merge_client_tools != null
                      ? ` · merge_client_tools: ${meta.request.merge_client_tools ? 'yes' : 'no'}`
                      : ''}
                  </summary>
                  <pre className="coreui-mono-block">{JSON.stringify(meta.request, null, 2)}</pre>
                </details>
              )}
              {Array.isArray(meta.steps) && meta.steps.length > 0 && (
                <div className="coreui-section-block">
                  <strong>Steps</strong>
                  {meta.steps.map((s, i) => (
                    <AgentTraceStepBlock key={i} step={s} index={i} />
                  ))}
                </div>
              )}
              {meta.final_message != null && (
                <div className="coreui-section-block coreui-stack-sm">
                  <strong>Final answer</strong>
                  <pre className="coreui-mono-block">
                    {meta.final_message.content != null && meta.final_message.content !== ''
                      ? meta.final_message.content
                      : '(no text content)'}
                  </pre>
                  {meta.final_message.finish_reason != null && (
                    <p className="dashboard-card-muted">finish_reason: {meta.final_message.finish_reason}</p>
                  )}
                </div>
              )}
            </>
          )}
          {!showRaw && !agentTraceStyle && meta && <ProxyRequestStructuredBody log={log} meta={meta} />}
          {!showRaw && !meta && (
            <p className="dashboard-card-muted">No metadata on this row (legacy or empty).</p>
          )}
        </div>
      </div>
    </div>
  );
}
