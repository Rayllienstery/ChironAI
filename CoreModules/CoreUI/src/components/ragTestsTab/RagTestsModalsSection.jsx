import React from 'react';
import { RagResultDetailModal, RagTestFormModal } from '../RagTestsModals';
import { metricVersionLabel, ragRetrieved, yesNo } from './helpers';

export default function RagTestsModalsSection(props) {
  const {
    runHistoryModal,
    setRunHistoryModal,
    runHistoryModalTab,
    setRunHistoryModalTab,
    formatRunDate,
    metricVersionLabel: _mvl,
    totalCount,
    passCount,
    failCount,
    ragRetrievedCount,
    groundingOverlapCount,
    strictRagOkCount,
    strictRagTotal,
    summaryBars,
    summaryBarMax,
    timingAverages,
    latencyStatsMs,
    renderTimingCards,
    fastestTests,
    slowestTests,
    topChunks,
    mostPopularChunk,
    topFailureReasons,
    failureMaxCount,
    allFailureReasons,
    runHistoryResults,
    exportRagTestRun,
    runCompareModal,
    setRunCompareModal,
    compareLeftRun,
    compareRightRun,
    compareSummaryRows,
    compareFmt,
    compareDeltaText,
    compareDeltaClass,
    compareFocus,
    setCompareFocus,
    compareOnlyDiff,
    setCompareOnlyDiff,
    compareVisiblePairs,
    comparePairs,
    compareRenderedPairs,
    compareHasTestDiff,
    compareSelectedDeltaText,
    compareConfidenceDeltaText,
    compareTpsDeltaText,
    resultDetailModal,
    setResultDetailModal,
    createOpen,
    setCreateOpen,
    createForm,
    setCreateForm,
    createConceptsWarning,
    handleCreateSubmit,
    createSubmitting,
    editOpen,
    setEditOpen,
    editTestId,
    setEditTestId,
    editForm,
    setEditForm,
    editConceptsWarning,
    handleEditSubmit,
    editSubmitting,
  } = props;
  return (
    <>
      {runHistoryModal && (
        <div
          className="rag-tests-modal rag-tests-result-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="rag-run-history-modal-title"
          onClick={() => setRunHistoryModal(null)}
        >
          <div
            className="rag-tests-modal-content rag-tests-result-modal-content"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="rag-tests-result-modal-header">
              <h3 id="rag-run-history-modal-title">Run details</h3>
              <button
                type="button"
                className="rag-tests-result-modal-close"
                onClick={() => setRunHistoryModal(null)}
                aria-label="Close"
              >
                &times;
              </button>
            </div>
            <p className="rag-tests-result-modal-meta">
              {formatRunDate(runHistoryModal.run?.created_at)} | Model: {runHistoryModal.run?.provider_id ? `${runHistoryModal.run?.provider_id} / ${runHistoryModal.run?.model}` : runHistoryModal.run?.model} | Passed: {runHistoryModal.run?.passed} | Failed: {runHistoryModal.run?.failed}
            </p>
            <p className="rag-tests-detail-metrics">
              Metrics: {metricVersionLabel(runHistoryModal.run)}
            </p>
            <div className="rag-tests-run-tabs">
              <button
                type="button"
                className={`rag-tests-btn small ${runHistoryModalTab === 'summary' ? 'primary' : ''}`}
                onClick={() => setRunHistoryModalTab('summary')}
              >
                Summary
              </button>
              <button
                type="button"
                className={`rag-tests-btn small ${runHistoryModalTab === 'tests' ? 'primary' : ''}`}
                onClick={() => setRunHistoryModalTab('tests')}
              >
                Tests
              </button>
            </div>
            <div className="rag-tests-past-run-actions">
              <button
                type="button"
                className="rag-tests-btn small"
                onClick={() => exportRagTestRun(runHistoryModal.id, 'json')}
                aria-label="Export run as JSON"
              >
                Export JSON
              </button>
              <button
                type="button"
                className="rag-tests-btn small"
                onClick={() => exportRagTestRun(runHistoryModal.id, 'csv')}
                aria-label="Export run as CSV"
              >
                Export CSV
              </button>
            </div>
            {runHistoryModalTab === 'summary' ? (
              <div className="rag-tests-run-summary">
                <div className="rag-tests-summary-kpis">
                  <div className="rag-tests-summary-kpi"><strong>Total:</strong> {totalCount}</div>
                  <div className="rag-tests-summary-kpi"><strong>Pass rate:</strong> {totalCount ? `${Math.round((passCount / totalCount) * 100)}%` : '-'}</div>
                  <div className="rag-tests-summary-kpi"><strong>Fail rate:</strong> {totalCount ? `${Math.round((failCount / totalCount) * 100)}%` : '-'}</div>
                  <div className="rag-tests-summary-kpi"><strong>RAG retrieved:</strong> {totalCount ? `${Math.round((ragRetrievedCount / totalCount) * 100)}%` : '-'}</div>
                  <div className="rag-tests-summary-kpi"><strong>Grounding overlap:</strong> {totalCount ? `${Math.round((groundingOverlapCount / totalCount) * 100)}%` : '-'}</div>
                  <div className="rag-tests-summary-kpi"><strong>Strict RAG OK:</strong> {strictRagTotal ? `${Math.round((strictRagOkCount / strictRagTotal) * 100)}%` : '-'}</div>
                </div>

                <section className="rag-tests-result-section">
                  <h4>Timing stats</h4>
                  {latencyStatsMs ? (
                    <div className="rag-tests-summary-kpis">
                      <div className="rag-tests-summary-kpi">avg: {Math.round(latencyStatsMs.avg)} ms</div>
                      <div className="rag-tests-summary-kpi">p50: {Math.round(latencyStatsMs.p50)} ms</div>
                      <div className="rag-tests-summary-kpi">p95: {Math.round(latencyStatsMs.p95)} ms</div>
                      <div className="rag-tests-summary-kpi">min: {Math.round(latencyStatsMs.min)} ms</div>
                      <div className="rag-tests-summary-kpi">max: {Math.round(latencyStatsMs.max)} ms</div>
                    </div>
                  ) : (
                    <p className="rag-tests-result-empty">No timing data.</p>
                  )}
                  {renderTimingCards(
                    timingAverages.map((item) => ({ key: item.label, value: item.value })),
                    'history-timing'
                  )}
                </section>

                <section className="rag-tests-result-section">
                  <h4>Outcome bars</h4>
                  <div className="rag-tests-summary-bars">
                    {summaryBars.map((item) => (
                      <div key={item.label} className="rag-tests-summary-bar-chart-row">
                        <span className="rag-tests-summary-bar-label">{item.label}</span>
                        <div className="rag-tests-summary-bar-track">
                          <div
                            className="rag-tests-summary-bar-fill"
                            style={{ width: `${summaryBarMax ? (item.value / summaryBarMax) * 100 : 0}%` }}
                          />
                        </div>
                        <span className="rag-tests-summary-bar-value">{item.value}</span>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="rag-tests-result-section">
                  <h4>Fastest tests</h4>
                  <ul className="rag-tests-rag-query-list">
                    {fastestTests.map((x) => (
                      <li key={`fast-${x.test_id}`}>
                        <span className="rag-tests-rag-query-meta">{x.test_name || x.test_id} | {Math.round(x.latency_ms)} ms</span>
                      </li>
                    ))}
                  </ul>
                  <h4>Slowest tests</h4>
                  <ul className="rag-tests-rag-query-list">
                    {slowestTests.map((x) => (
                      <li key={`slow-${x.test_id}`}>
                        <span className="rag-tests-rag-query-meta">{x.test_name || x.test_id} | {Math.round(x.latency_ms)} ms</span>
                      </li>
                    ))}
                  </ul>
                </section>

                <section className="rag-tests-result-section">
                  <h4>Most popular RAG chunk</h4>
                  {mostPopularChunk ? (
                    <p className="rag-tests-detail-metrics">
                      {mostPopularChunk.key} | count {mostPopularChunk.count} | avg score {mostPopularChunk.avgScore != null ? mostPopularChunk.avgScore.toFixed(3) : '-'}
                    </p>
                  ) : (
                    <p className="rag-tests-result-empty">No RAG chunks in this run.</p>
                  )}
                </section>

                <section className="rag-tests-result-section">
                  <h4>Top failure reasons</h4>
                  {topFailureReasons.length === 0 ? (
                    <p className="rag-tests-result-empty">No failures in this run.</p>
                  ) : (
                    <div className="rag-tests-summary-bars">
                      {topFailureReasons.map((fr) => (
                        <div key={fr.normalized} className="rag-tests-summary-bar-chart-row">
                          <span className="rag-tests-summary-bar-label">{fr.sample}</span>
                          <div className="rag-tests-summary-bar-track">
                            <div
                              className="rag-tests-summary-bar-fill fail"
                              style={{ width: `${failureMaxCount ? (fr.count / failureMaxCount) * 100 : 0}%` }}
                            />
                          </div>
                          <span className="rag-tests-summary-bar-value">{fr.count}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </section>

                <section className="rag-tests-result-section">
                  <h4>All failure reasons</h4>
                  {allFailureReasons.length === 0 ? (
                    <p className="rag-tests-result-empty">No failures in this run.</p>
                  ) : (
                    <ul className="rag-tests-rag-query-list">
                      {allFailureReasons.map((fr) => (
                        <li key={`all-${fr.normalized}`}>
                          <span className="rag-tests-rag-query-meta">{fr.sample} | count {fr.count}</span>
                          {fr.tests?.length ? (
                            <p className="rag-tests-detail-metrics">Examples: {fr.tests.join(', ')}</p>
                          ) : null}
                        </li>
                      ))}
                    </ul>
                  )}
                </section>
              </div>
            ) : (
              <table className="rag-tests-history-table" role="table">
                <thead>
                  <tr>
                    <th>Test name</th>
                    <th>Status</th>
                    <th>Time (ms)</th>
                    <th>Tok/s</th>
                    <th>RAG retrieved</th>
                    <th>Grounding</th>
                    <th>Strict</th>
                    <th>Quote</th>
                    <th>Confidence</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {(runHistoryModal.run?.results || []).map((row) => (
                    <tr key={`${row.test_id}-${row.status}-${row.response_time_ms || 0}`}>
                      <td>{row.test_name || row.test_id}</td>
                      <td>
                        <span className={`rag-tests-status ${(row.status || '').toLowerCase()}`}>
                          {row.status || '-'}
                        </span>
                      </td>
                      <td>{row.response_time_ms != null ? row.response_time_ms : '-'}</td>
                      <td>
                        {row.tokens_per_second_generated != null
                          ? Number(row.tokens_per_second_generated).toFixed(2)
                          : '-'}
                      </td>
                      <td>{yesNo(ragRetrieved(row))}</td>
                      <td>{yesNo(row.grounding_overlap)}</td>
                      <td>{yesNo(row.strict_mode)}</td>
                      <td>{yesNo(row.strict_quote_ok)}</td>
                      <td>{row.confidence_label || '-'}</td>
                      <td>
                        <button
                          type="button"
                          className="coreui-btn coreui-btn-primary coreui-btn-small"
                          onClick={() => setResultDetailModal({
                            test: {
                              id: row.test_id,
                              name: row.test_name,
                              platform: row.platform,
                              framework: row.framework,
                              difficulty: row.difficulty || '',
                              question: row.question || '',
                            },
                            last: row,
                          })}
                        >
                          Details
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}

      {runCompareModal && (
        <div
          className="rag-tests-modal rag-tests-result-modal rag-tests-compare-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="rag-run-compare-modal-title"
          onClick={() => setRunCompareModal(null)}
        >
          <div
            className="rag-tests-modal-content rag-tests-result-modal-content rag-tests-compare-modal-content"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="rag-tests-result-modal-header">
              <h3 id="rag-run-compare-modal-title">Run compare</h3>
              <button
                type="button"
                className="rag-tests-result-modal-close"
                onClick={() => setRunCompareModal(null)}
                aria-label="Close"
              >
                &times;
              </button>
            </div>
            <div className="rag-tests-compare-run-cards">
              <section className="rag-tests-compare-run-card">
                <h4>Left run</h4>
                <p className="rag-tests-result-modal-meta">
                  {formatRunDate(compareLeftRun?.created_at)} | Model: {compareLeftRun?.provider_id ? `${compareLeftRun?.provider_id} / ${compareLeftRun?.model}` : (compareLeftRun?.model || '-')}
                </p>
                <p className="rag-tests-detail-metrics">id: {String(runCompareModal.left?.id || '-')}</p>
                <p className="rag-tests-detail-metrics">metrics: {metricVersionLabel(compareLeftRun)}</p>
              </section>
              <section className="rag-tests-compare-vs">+ / -</section>
              <section className="rag-tests-compare-run-card">
                <h4>Right run</h4>
                <p className="rag-tests-result-modal-meta">
                  {formatRunDate(compareRightRun?.created_at)} | Model: {compareRightRun?.provider_id ? `${compareRightRun?.provider_id} / ${compareRightRun?.model}` : (compareRightRun?.model || '-')}
                </p>
                <p className="rag-tests-detail-metrics">id: {String(runCompareModal.right?.id || '-')}</p>
                <p className="rag-tests-detail-metrics">metrics: {metricVersionLabel(compareRightRun)}</p>
              </section>
            </div>

            <section className="rag-tests-result-section">
              <h4>Summary diff</h4>
              <div className="rag-tests-compare-table">
                <div className="rag-tests-compare-head">Left</div>
                <div className="rag-tests-compare-head">Δ</div>
                <div className="rag-tests-compare-head">Right</div>
                {compareSummaryRows.map((row) => {
                  const digits = row.key.includes('rate') || row.key.includes('tps') ? 2 : 0;
                  const delta = compareDeltaText(row.left, row.right, row.higherIsBetter, digits);
                  return (
                    <div key={`sum-${row.key}`} className="rag-tests-compare-row">
                      <div className="rag-tests-compare-cell">
                        <strong>{row.label}:</strong> {compareFmt(row.left, digits)}
                      </div>
                      <div className={`rag-tests-compare-delta ${compareDeltaClass(delta)}`}>
                        {delta}
                      </div>
                      <div className="rag-tests-compare-cell">
                        <strong>{row.label}:</strong> {compareFmt(row.right, digits)}
                      </div>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="rag-tests-result-section">
              <div className="rag-tests-compare-toolbar">
                <h4>Per-test diff ({compareVisiblePairs.length}/{comparePairs.length})</h4>
                <div className="rag-tests-run-tabs rag-tests-compare-focus-tabs" role="tablist" aria-label="Compare focus">
                  <button
                    type="button"
                    className={`rag-tests-btn small ${compareFocus === 'status' ? 'primary' : ''}`}
                    onClick={() => setCompareFocus('status')}
                    role="tab"
                    aria-selected={compareFocus === 'status'}
                  >
                    Success/Fail
                  </button>
                  <button
                    type="button"
                    className={`rag-tests-btn small ${compareFocus === 'latency' ? 'primary' : ''}`}
                    onClick={() => setCompareFocus('latency')}
                    role="tab"
                    aria-selected={compareFocus === 'latency'}
                  >
                    Latency
                  </button>
                  <button
                    type="button"
                    className={`rag-tests-btn small ${compareFocus === 'tps' ? 'primary' : ''}`}
                    onClick={() => setCompareFocus('tps')}
                    role="tab"
                    aria-selected={compareFocus === 'tps'}
                  >
                    Tok/s
                  </button>
                  <button
                    type="button"
                    className={`rag-tests-btn small ${compareFocus === 'confidence' ? 'primary' : ''}`}
                    onClick={() => setCompareFocus('confidence')}
                    role="tab"
                    aria-selected={compareFocus === 'confidence'}
                  >
                    Confidence n/m
                  </button>
                </div>
                <label className="rag-tests-checkbox-label">
                  <input
                    type="checkbox"
                    checked={compareOnlyDiff}
                    onChange={(e) => setCompareOnlyDiff(e.target.checked)}
                  />
                  Only differences
                </label>
              </div>
              <div className="rag-tests-compare-tests">
                {compareRenderedPairs.map((pair) => {
                  const left = pair?.left || null;
                  const right = pair?.right || null;
                  const title = left?.test_name || right?.test_name || pair?.pairKey || '-';
                  const leftStatus = String(left?.status || '-');
                  const rightStatus = String(right?.status || '-');
                  const leftLatency = Number(left?.latency_ms ?? left?.response_time_ms);
                  const rightLatency = Number(right?.latency_ms ?? right?.response_time_ms);
                  const latencyDelta = Number.isFinite(leftLatency) && Number.isFinite(rightLatency)
                    ? compareDeltaText(leftLatency, rightLatency, false, 0)
                    : '·';
                  const statusDelta = leftStatus === rightStatus
                    ? '±0'
                    : (leftStatus === 'PASS' && rightStatus === 'FAIL')
                      ? '- FAIL'
                      : (leftStatus === 'FAIL' && rightStatus === 'PASS')
                        ? '+ PASS'
                        : `${leftStatus}→${rightStatus}`;
                  const selectedDelta = compareSelectedDeltaText(left, right, statusDelta, latencyDelta);
                  const selectedDeltaClass = compareDeltaClass(selectedDelta);
                  const statusDeltaClass = compareDeltaClass(statusDelta);
                  const latencyDeltaClass = compareDeltaClass(latencyDelta);
                  return (
                    <article key={`cmp-${pair?.pairKey || title}`} className="rag-tests-compare-test-row">
                      <div className="rag-tests-compare-cell">
                        <p className="rag-tests-rag-query-meta">{title}</p>
                        <p className="rag-tests-detail-metrics">
                          status: {leftStatus} | latency: {Number.isFinite(leftLatency) ? `${Math.round(leftLatency)} ms` : '-'} | tok/s: {left?.tokens_per_second_generated != null ? Number(left.tokens_per_second_generated).toFixed(2) : '-'} | retrieved: {yesNo(ragRetrieved(left))} | grounded: {yesNo(left?.grounding_overlap)}
                        </p>
                        <p className="rag-tests-detail-metrics">
                          confidence: {left?.confidence_label || '-'} | reason: {left?.failure_reason || left?.error || '-'}
                        </p>
                      </div>
                      <div className={`rag-tests-compare-delta rag-tests-compare-delta-stack ${selectedDeltaClass}`}>
                        <span className={`rag-tests-compare-delta-value ${selectedDeltaClass}`}>{selectedDelta}</span>
                        <span className={`rag-tests-compare-delta-value ${latencyDeltaClass}`}>{latencyDelta}</span>
                        <span className={`rag-tests-compare-delta-value ${statusDeltaClass}`}>{statusDelta}</span>
                      </div>
                      <div className="rag-tests-compare-cell">
                        <p className="rag-tests-rag-query-meta">{title}</p>
                        <p className="rag-tests-detail-metrics">
                          status: {rightStatus} | latency: {Number.isFinite(rightLatency) ? `${Math.round(rightLatency)} ms` : '-'} | tok/s: {right?.tokens_per_second_generated != null ? Number(right.tokens_per_second_generated).toFixed(2) : '-'} | retrieved: {yesNo(ragRetrieved(right))} | grounded: {yesNo(right?.grounding_overlap)}
                        </p>
                        <p className="rag-tests-detail-metrics">
                          confidence: {right?.confidence_label || '-'} | reason: {right?.failure_reason || right?.error || '-'}
                        </p>
                      </div>
                    </article>
                  );
                })}
              </div>
            </section>
          </div>
        </div>
      )}

      <RagResultDetailModal
        detail={resultDetailModal}
        onClose={() => setResultDetailModal(null)}
      />
      <RagTestFormModal
        open={createOpen}
        title="Create RAG test"
        form={createForm}
        onFormChange={setCreateForm}
        conceptsWarning={createConceptsWarning}
        onSubmit={handleCreateSubmit}
        onClose={() => setCreateOpen(false)}
        submitting={createSubmitting}
        submitLabel={{ idle: 'Create', pending: 'Creating...' }}
      />
      <RagTestFormModal
        open={editOpen}
        title="Edit RAG test"
        form={editForm}
        onFormChange={setEditForm}
        conceptsWarning={editConceptsWarning}
        onSubmit={handleEditSubmit}
        onClose={() => {
          setEditOpen(false);
          setEditTestId(null);
        }}
        submitting={editSubmitting}
        submitLabel={{ idle: 'Save', pending: 'Saving...' }}
      />

    </>
  );
}
