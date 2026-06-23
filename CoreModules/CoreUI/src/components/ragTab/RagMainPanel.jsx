import React from 'react';
import RagPipelineOverview from '../RagPipelineOverview';
import RagTraceTimeline from '../RagTraceTimeline';

export default function RagMainPanel({ status, ragModelSettings, mirroredPipelineTrace }) {
  return (
        <>
          {status && (
            <div className="rag-status-grid">
              <div className="rag-status-card">
                <div className="label">Endpoint</div>
                <div className="value">{status.url}</div>
              </div>
              <div className="rag-status-card">
                <div className="label">Running</div>
                <div className="value">{status.running ? 'Yes' : 'No'}</div>
              </div>
              <div className="rag-status-card">
                <div className="label">Collections</div>
                <div className="value">{status.collections_count ?? '—'}</div>
              </div>
              {status.version && (
                <div className="rag-status-card">
                  <div className="label">Version</div>
                  <div className="value">{status.version}</div>
                </div>
              )}
            </div>
          )}

          <section
            className="rag-pipeline-overview-section"
            aria-labelledby="rag-pipeline-overview-heading"
          >
            <h3 id="rag-pipeline-overview-heading" className="rag-pipeline-mirror-title">
              RAG pipeline map (how it runs, in order)
            </h3>
            <p className="rag-pipeline-mirror-hint">
              This is a <strong>static</strong> description of the server-side retrieval path: the same sequence applies to
              every RAG-backed request; only the timings and which optional branches actually run change per call.{' '}
              <strong>Highlighting</strong> reflects your current <strong>Models for RAG / Qdrant</strong> card (saved flags):{' '}
              <span className="rag-pipeline-legend rag-pipeline-legend--core">always runs</span>
              {' · '}
              <span className="rag-pipeline-legend rag-pipeline-legend--on">optional, on</span>
              {' · '}
              <span className="rag-pipeline-legend rag-pipeline-legend--off">optional, off</span>
              . Sub-badges (e.g. hybrid sparse, structured layout) apply on top of a core step. The live trace merges
              gate/retry hints into <strong>Context assembly</strong>; this map lists every stage. For timings, use{' '}
              <strong>Testing</strong> → Model Tester with <strong>Use RAG</strong>.
            </p>
            <RagPipelineOverview pipelineSettings={ragModelSettings} />
          </section>

          <section
            className="rag-pipeline-mirror-section"
            aria-labelledby="rag-pipeline-mirror-heading"
          >
            <h3 id="rag-pipeline-mirror-heading" className="rag-pipeline-mirror-title">
              Last run timeline (with timings)
            </h3>
            <p className="rag-pipeline-mirror-hint">
              Send a message in <strong>Testing</strong> → <strong>Model Tester</strong> with <strong>Use RAG</strong>{' '}
              enabled. The live timeline appears there immediately; this card mirrors the <strong>most recent</strong>{' '}
              captured trace (per-step latency and skip reasons when applicable).
            </p>
            {mirroredPipelineTrace?.steps?.length > 0 ? (
              <RagTraceTimeline
                steps={mirroredPipelineTrace.steps}
                title="Last RAG pipeline"
                totalLatencyMs={mirroredPipelineTrace.latencyMs ?? undefined}
              />
            ) : (
              <p className="rag-pipeline-mirror-empty">
                No trace yet — open Testing, enable Use RAG, send a message, then return here or stay on Testing to see
                steps.
              </p>
            )}
          </section>
        </>
  );
}
