import React from 'react';
import Card from '../Card';

export default function RagTestsLiveSection(props) {
  const {
    liveMonitorOpen,
    setLiveMonitorOpen,
    liveCards,
    getLiveStepRows,
    renderTimingCards,
    setLiveDetailCardIndex,
    openLiveDetail,
    liveMonitorDetailOpen,
    setLiveMonitorDetailOpen,
    selectedLiveDetailCard,
    runProgress,
    selectedLiveStepRows,
    liveSse,
    liveTraceQuery,
    liveTraceChunks,
  } = props;
  return (
    <>
      <div className="rag-tests-live-monitor">
        <button
          type="button"
          className="rag-tests-history-toggle"
          onClick={() => setLiveMonitorOpen((v) => !v)}
          aria-expanded={liveMonitorOpen}
        >
          {liveMonitorOpen ? '[-]' : '[+]'} Live test monitor
        </button>
        {liveMonitorOpen && (
          <Card
            className="rag-tests-live-monitor-panel"
            elevation="var(--md-sys-elevation-level1)"
            onClick={openLiveDetail}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                openLiveDetail();
              }
            }}
          >
            <div className="rag-tests-live-monitor-scroll">
              {liveCards.map((card) => {
                const stepRows = getLiveStepRows(card);
                return (
                  <section key={`live-card-${card.index}`} className="rag-tests-live-card">
                    <p className="rag-tests-live-line">
                      <strong>Current step:</strong> {card.name || 'idle'}
                    </p>
                    <p className="rag-tests-live-line">
                      <strong>Tokens/s:</strong>{' '}
                      live {card?.sse_token_tps_live != null ? `${Number(card.sse_token_tps_live).toFixed(2)}` : '-'} | avg {card?.sse_token_tps_avg != null ? `${Number(card.sse_token_tps_avg).toFixed(2)}` : '-'}
                    </p>
                    <p className="rag-tests-live-line">
                      <strong>Generated tokens:</strong>{' '}
                      {card?.sse_tokens_generated_est != null ? Number(card.sse_tokens_generated_est).toLocaleString() : '-'}
                    </p>
                    <p className="rag-tests-live-line">
                      <strong>Current test timings:</strong>
                    </p>
                    {renderTimingCards(stepRows, `card-${card.index}`)}
                    <div className="rag-tests-live-actions">
                      <button
                        type="button"
                        className="coreui-btn coreui-btn-primary coreui-btn-small"
                        onClick={(e) => {
                          e.stopPropagation();
                          setLiveDetailCardIndex(card.index);
                          openLiveDetail();
                        }}
                      >
                        Details
                      </button>
                    </div>
                  </section>
                );
              })}
            </div>
          </Card>
        )}
      </div>

      {liveMonitorDetailOpen && (
        <div
          className="rag-tests-modal rag-tests-result-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="rag-live-monitor-modal-title"
          onClick={() => setLiveMonitorDetailOpen(false)}
        >
          <div
            className="rag-tests-modal-content rag-tests-result-modal-content"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="rag-tests-result-modal-header">
              <h3 id="rag-live-monitor-modal-title">Live test monitor details</h3>
              <button
                type="button"
                className="rag-tests-result-modal-close"
                onClick={() => setLiveMonitorDetailOpen(false)}
                aria-label="Close"
              >
                &times;
              </button>
            </div>
            <p className="rag-tests-result-modal-meta">
              Current test: <strong>{selectedLiveDetailCard?.name || runProgress?.current_test_name || 'idle'}</strong>
            </p>
            <section className="rag-tests-result-section">
              <h4>Current stage timings</h4>
              {renderTimingCards(selectedLiveStepRows, 'modal')}
            </section>
            <section className="rag-tests-result-section">
              <h4>SSE streaming</h4>
              <p className="rag-tests-detail-metrics">
                live {selectedLiveDetailCard?.sse_token_tps_live != null ? `${Number(selectedLiveDetailCard.sse_token_tps_live).toFixed(2)} tok/s` : '-'} | avg {selectedLiveDetailCard?.sse_token_tps_avg != null ? `${Number(selectedLiveDetailCard.sse_token_tps_avg).toFixed(2)} tok/s` : '-'}
              </p>
              {(selectedLiveDetailCard?.sse_preview || liveSse.text) ? (
                <pre className="rag-tests-pre rag-tests-pre-answer">{selectedLiveDetailCard?.sse_preview || liveSse.text}</pre>
              ) : (
                <p className="rag-tests-result-empty">No stream chunks yet.</p>
              )}
            </section>
            <section className="rag-tests-result-section">
              <h4>RAG request</h4>
              {liveTraceQuery ? (
                <pre className="rag-tests-pre rag-tests-pre-tight">{liveTraceQuery}</pre>
              ) : (
                <p className="rag-tests-result-empty">Request preview not available yet.</p>
              )}
            </section>
            <section className="rag-tests-result-section">
              <h4>RAG chunks</h4>
              {liveTraceChunks.length === 0 ? (
                <p className="rag-tests-result-empty">No chunks captured yet.</p>
              ) : (
                <ul className="rag-tests-chunks rag-tests-chunks-modal">
                  {liveTraceChunks.map((ch, idx) => (
                    <li key={`live-chunk-${idx}`}>
                      <span className="rag-tests-chunk-meta">
                        #{idx + 1} score={ch?.score ?? 'N/A'} {ch?.url ? `url=${ch.url}` : ''} {ch?.source ? `source=${ch.source}` : ''}
                      </span>
                      <pre className="rag-tests-pre small">
                        {ch?.text_preview || ch?.text || ''}
                      </pre>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          </div>
        </div>
      )}

    </>
  );
}
