import React from 'react';
import '../styles/components/RagTraceTimeline.css';

/** Shared with ModelTester + RagTab: persist last trace for the RAG tab mirror. */
export const CHIRONAI_RAG_TRACE_STORAGE_KEY = 'chironai_last_rag_trace';
export const CHIRONAI_RAG_TRACE_EVENT = 'chironai-rag-trace';

function iconClassForStep(id) {
  const s = String(id || '');
  if (s === 'rag_skipped') return 'skip';
  if (s === 'query_prep') return 'prep';
  if (s === 'embed_search_pass1') return 'search';
  if (s === 'concept_expansion_pass2') return 'expand';
  if (s === 'metadata_rank') return 'meta';
  if (s === 'rerank') return 'rerank';
  if (s === 'coverage_selection') return 'coverage';
  if (s === 'coverage_metrics') return 'metrics';
  if (s === 'coverage_gate') return 'gate';
  if (s === 'coverage_supplemental') return 'supplemental';
  if (s === 'context_assembly') return 'context';
  if (s === 'answer_generation') return 'chat';
  return 'context';
}

function glyphForStep(id) {
  const s = String(id || '');
  if (s === 'rag_skipped') return '—';
  if (s === 'query_prep') return '¶';
  if (s === 'embed_search_pass1') return '◎';
  if (s === 'concept_expansion_pass2') return '↻';
  if (s === 'metadata_rank') return '≡';
  if (s === 'rerank') return '↕';
  if (s === 'coverage_selection') return '◫';
  if (s === 'coverage_metrics') return '%';
  if (s === 'coverage_gate') return '⧗';
  if (s === 'coverage_supplemental') return '⎘';
  if (s === 'context_assembly') return '▤';
  if (s === 'answer_generation') return '◆';
  return '•';
}

function formatDurationMs(ms) {
  if (ms == null) return '—';
  const n = Number(ms);
  if (Number.isNaN(n)) return '—';
  if (n < 1000) return `${n} ms`;
  return `${(n / 1000).toFixed(2)} s`;
}

/**
 * Vertical timeline for RAG pipeline steps (Creative Tim Material Dashboard "Orders overview" style).
 * Expects API `rag_trace`: { id, label, status, duration_ms?, detail? }[]
 * Set showDurations={false} for static overview maps (detail only).
 */
export default function RagTraceTimeline({
  steps,
  title = 'RAG pipeline',
  totalLatencyMs,
  showDurations = true,
  overviewMode = false,
}) {
  if (!Array.isArray(steps) || steps.length === 0) return null;

  const subtitle =
    typeof totalLatencyMs === 'number' && totalLatencyMs >= 0 ? (
      <>
        <strong>{totalLatencyMs} ms</strong> end-to-end (request)
      </>
    ) : null;

  const titleTrimmed = title != null ? String(title).trim() : '';
  const hasHeader = Boolean(titleTrimmed) || Boolean(subtitle);

  return (
    <div
      className={`rag-trace-card${overviewMode ? ' rag-trace-card--overview' : ''}`}
      aria-label={overviewMode ? 'RAG pipeline overview' : 'RAG retrieval pipeline steps'}
    >
      {hasHeader ? (
        <div className="rag-trace-card-header">
          {titleTrimmed ? <h3 className="rag-trace-card-title">{titleTrimmed}</h3> : null}
          {subtitle && <p className="rag-trace-card-subtitle">{subtitle}</p>}
        </div>
      ) : null}
      <ul className="rag-trace-list">
        {steps.map((step, i) => {
          const ic = iconClassForStep(step.id);
          const status = String(step.status || 'ok');
          const durSkippedNull =
            status === 'skipped' && (step.duration_ms == null || step.duration_ms === '');
          const dur = durSkippedNull ? null : step.duration_ms;
          let subtitleLine = '';
          if (showDurations) {
            const parts = [formatDurationMs(dur)];
            if (step.detail) parts.push(String(step.detail));
            subtitleLine = parts.join(' · ');
          } else if (step.detail) {
            subtitleLine = String(step.detail);
          }
          const iconSkip =
            status === 'skipped' && step.id !== 'rag_skipped' ? ' rag-trace-icon--optional' : '';
          const band = overviewMode && step.overviewBand ? String(step.overviewBand) : '';
          const badges = overviewMode && Array.isArray(step.overviewBadges) ? step.overviewBadges : [];
          const liClass = ['rag-trace-item', band ? `rag-trace-item--overview-${band}` : '']
            .filter(Boolean)
            .join(' ');
          return (
            <li key={step.id != null ? String(step.id) : `step-${i}`} className={liClass}>
              <div
                className={`rag-trace-icon rag-trace-icon--${ic}${
                  status === 'skipped' ? ' rag-trace-icon--skip' : ''
                }${iconSkip}`}
                aria-hidden
              >
                {glyphForStep(step.id)}
              </div>
              <div className="rag-trace-body">
                <div className="rag-trace-title">{step.label || step.id || 'Step'}</div>
                {badges.length > 0 ? (
                  <div className="rag-trace-overview-badges" aria-label="Active sub-options">
                    {badges.map((b) => (
                      <span key={b} className="rag-trace-overview-badge">
                        {b}
                      </span>
                    ))}
                  </div>
                ) : null}
                {subtitleLine ? <div className="rag-trace-subtitle">{subtitleLine}</div> : null}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
