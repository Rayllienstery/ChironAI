import React from 'react';

export default function RagTestsHistorySection(props) {
  const {
    historySectionOpen,
    setHistorySectionOpen,
    runSummary,
    runHistory,
    historyFilters,
    setHistoryFilters,
    providerCatalog,
    runHistoryLoading,
    compareRunIds,
    toggleCompareRun,
    formatRunDate,
    handleSelectPastRun,
    runHistoryHasMore,
    runHistoryLoadingMore,
    loadRunHistory,
    runHistoryDeleteLoading,
    handleDeleteCancelledRuns,
    handleDeleteLowPassRuns,
    handleDeleteSelectedRuns,
    clearCompareRuns,
    runCompareLoading,
    handleOpenRunCompare,
  } = props;
  return (
      <div className="rag-tests-history-section">
        <button
          type="button"
          className="rag-tests-btn"
          onClick={() => setHistorySectionOpen(true)}
        >
          Run history
        </button>
        {historySectionOpen && (
          <div
            className="rag-tests-modal rag-tests-result-modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rag-run-history-list-title"
            onClick={() => setHistorySectionOpen(false)}
          >
            <div
              className="rag-tests-modal-content rag-tests-result-modal-content"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="rag-tests-result-modal-header">
                <h3 id="rag-run-history-list-title">Run history</h3>
                <button
                  type="button"
                  className="rag-tests-result-modal-close"
                  onClick={() => setHistorySectionOpen(false)}
                  aria-label="Close"
                >
                  &times;
                </button>
              </div>
              <div className="rag-tests-history-panel">
            {runSummary && (
              <div className="rag-tests-summary-block">
                <p className="rag-tests-summary-line">
                  Last {runSummary.total_runs} runs: {runSummary.total_tests} total tests, {runSummary.pass_rate_pct}% pass rate
                </p>
                {runSummary.retrieval_rate_pct != null && (
                  <p className="rag-tests-summary-line">
                    RAG retrieved: {runSummary.retrieval_rate_pct}% | Grounding overlap: {runSummary.grounding_overlap_rate_pct ?? 0}%
                  </p>
                )}
                {runSummary.per_model?.length > 0 && (
                  <p className="rag-tests-summary-line">
                    By model: {runSummary.per_model.map((m) => `${m.provider_id ? `${m.provider_id} / ` : ''}${m.model} ${m.pass_rate_pct}%`).join(', ')}
                  </p>
                )}
                {runSummary.domains?.length > 0 && (
                  <div className="rag-tests-summary-domains">
                    {runSummary.domains.map((d) => (
                      <div key={d.domain} className="rag-tests-domain-card">
                        <div className="rag-tests-domain-header">
                          <span className="rag-tests-domain-name">{d.domain}</span>
                          <span className="rag-tests-domain-pass-rate">{d.pass_rate_pct}% PASS</span>
                        </div>
                        <div className="rag-tests-domain-bar" aria-label={`Domain ${d.domain} pass/fail`}>
                          <div
                            className="rag-tests-domain-bar-pass"
                            style={{ width: d.total ? `${(d.passed / d.total) * 100}%` : '0%' }}
                          />
                          <div
                            className="rag-tests-domain-bar-fail"
                            style={{ width: d.total ? `${(d.failed / d.total) * 100}%` : '0%' }}
                          />
                        </div>
                        {d.by_difficulty?.length > 0 && (
                          <div className="rag-tests-domain-difficulties">
                            {d.by_difficulty.map((diff) => (
                              <div key={diff.difficulty} className="rag-tests-domain-diff-row">
                                <span className="rag-tests-domain-diff-label">{diff.difficulty}</span>
                                <span className="rag-tests-domain-diff-value">
                                  {diff.pass_rate_pct}% ({diff.passed}/{diff.total})
                                </span>
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
                {runHistory.length > 1 && (
                  <p className="rag-tests-summary-line">
                    Trend (last 3 runs):{' '}
                    {runHistory
                      .slice(0, 3)
                      .map((r) => {
                        const total = (r.total || 0);
                        const passRate = total ? Math.round(((r.passed || 0) / total) * 100) : 0;
                        return `${formatRunDate(r.created_at)}: ${passRate}%`;
                      })
                      .join(' -> ')}
                  </p>
                )}
              </div>
            )}
            <div className="rag-tests-history-filters">
              <label>
                Provider
                <select
                  value={historyFilters.provider_id}
                  onChange={(e) => setHistoryFilters((f) => ({ ...f, provider_id: e.target.value }))}
                  className="rag-tests-select"
                  aria-label="Filter by provider"
                >
                  <option value="">All</option>
                  {[...new Set(runHistory.map((r) => r.provider_id).filter(Boolean))].sort().map((providerId) => (
                    <option key={providerId} value={providerId}>{providerId}</option>
                  ))}
                </select>
              </label>
              <label>
                Model
                <select
                  value={historyFilters.model}
                  onChange={(e) => setHistoryFilters((f) => ({ ...f, model: e.target.value }))}
                  className="rag-tests-select"
                  aria-label="Filter by model"
                >
                  <option value="">All</option>
                  {[...new Set(runHistory.map((r) => r.model).filter(Boolean))].sort().map((m) => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
              </label>
              <label>
                From date
                <input
                  type="date"
                  value={historyFilters.from_date}
                  onChange={(e) => setHistoryFilters((f) => ({ ...f, from_date: e.target.value }))}
                  className="rag-tests-input"
                  aria-label="Filter from date"
                />
              </label>
              <label>
                To date
                <input
                  type="date"
                  value={historyFilters.to_date}
                  onChange={(e) => setHistoryFilters((f) => ({ ...f, to_date: e.target.value }))}
                  className="rag-tests-input"
                  aria-label="Filter to date"
                />
              </label>
              <label>
                Status
                <select
                  value={historyFilters.status}
                  onChange={(e) => setHistoryFilters((f) => ({ ...f, status: e.target.value }))}
                  className="rag-tests-select"
                  aria-label="Filter by status"
                >
                  <option value="">All</option>
                  <option value="completed">completed</option>
                  <option value="cancelled">cancelled</option>
                </select>
              </label>
            </div>
            <div className="rag-tests-history-delete-actions">
              <button
                type="button"
                className="rag-tests-btn small"
                disabled={runHistoryDeleteLoading}
                onClick={() => void handleDeleteCancelledRuns()}
              >
                Delete cancelled
              </button>
              <button
                type="button"
                className="rag-tests-btn small"
                disabled={runHistoryDeleteLoading}
                onClick={() => void handleDeleteLowPassRuns()}
              >
                Delete &lt;25% passed
              </button>
              <button
                type="button"
                className="rag-tests-btn small"
                disabled={runHistoryDeleteLoading || compareRunIds.length === 0}
                onClick={() => void handleDeleteSelectedRuns()}
              >
                Delete selected
              </button>
            </div>
            <div className="rag-tests-history-compare-actions">
              <span className="rag-tests-history-compare-selected">
                Selected: {compareRunIds.length}/2
                {compareRunIds.length > 0 ? ` (${compareRunIds.join(' vs ')})` : ''}
              </span>
              <button
                type="button"
                className="rag-tests-btn small"
                disabled={compareRunIds.length === 0}
                onClick={clearCompareRuns}
              >
                Clear
              </button>
              <button
                type="button"
                className="rag-tests-btn small primary"
                disabled={compareRunIds.length !== 2 || runCompareLoading}
                onClick={() => void handleOpenRunCompare()}
              >
                {runCompareLoading ? 'Opening…' : 'Compare selected'}
              </button>
            </div>
            {runHistoryLoading ? (
              <p className="rag-tests-history-loading">Loading history...</p>
            ) : runHistory.length === 0 ? (
              <p className="rag-tests-history-empty">No past runs yet.</p>
            ) : (
              <>
              <table className="rag-tests-history-table" role="table">
                <thead>
                  <tr>
                    <th>Cmp</th>
                    <th>Date</th>
                    <th>Model</th>
                    <th>Total</th>
                    <th>Passed</th>
                    <th>Failed</th>
                    <th>Status</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {runHistory.map((run) => (
                    <tr
                      key={run.id}
                      className={`rag-tests-history-row ${compareRunIds.includes(String(run.id)) ? 'selected' : ''}`}
                    >
                      <td>
                        <input
                          type="checkbox"
                          checked={compareRunIds.includes(String(run.id))}
                          onChange={() => toggleCompareRun(run.id)}
                          aria-label={`Select run ${run.id} for compare`}
                        />
                      </td>
                      <td>{formatRunDate(run.created_at)}</td>
                      <td>{run.provider_id ? `${run.provider_id} / ${run.model}` : run.model}</td>
                      <td>{run.total}</td>
                      <td className="rag-tests-stat-passed">{run.passed}</td>
                      <td className="rag-tests-stat-failed">{run.failed}</td>
                      <td><span className={`rag-tests-status ${run.status}`}>{run.status}</span></td>
                      <td>
                        <button
                          type="button"
                          className="rag-tests-btn small"
                          onClick={() => handleSelectPastRun(run.id)}
                        >
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {runHistoryHasMore && (
                <div className="rag-tests-history-load-more">
                  <button
                    type="button"
                    className="rag-tests-btn"
                    disabled={runHistoryLoadingMore}
                    onClick={() => loadRunHistory(runHistory.length)}
                  >
                    {runHistoryLoadingMore ? 'Loading...' : 'Load more'}
                  </button>
                </div>
              )}
              </>
            )}
              </div>
            </div>
          </div>
        )}
      </div>

  );
}
