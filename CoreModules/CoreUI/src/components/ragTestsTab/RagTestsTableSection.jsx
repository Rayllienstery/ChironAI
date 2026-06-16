import React from 'react';
import Card from '../Card';
import { ragRetrieved, yesNo } from './helpers';

export default function RagTestsTableSection(props) {
  const {
    running,
    filters,
    setFilters,
    filterOptions,
    filteredTests,
    selectedTestIds,
    toggleSelectAll,
    toggleSelectTest,
    tableRows,
    lastResultByTestId,
    handleRunSingle,
    canRun,
    setResultDetailModal,
    handleEditClick,
    handleDeleteClick,
    failResults,
    showFailDrilldown,
    setShowFailDrilldown,
    failFilters,
    setFailFilters,
    error,
    runError,
  } = props;
  return (
    <>
      {!running && (
        <div className="rag-tests-filters">
          <label>
            Platform
            <select
              value={filters.platform}
              onChange={(e) => setFilters((f) => ({ ...f, platform: e.target.value }))}
              className="rag-tests-select"
              aria-label="Filter by platform"
            >
              <option value="">All</option>
              {(filterOptions.platform || []).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label>
            Framework
            <select
              value={filters.framework}
              onChange={(e) => setFilters((f) => ({ ...f, framework: e.target.value }))}
              className="rag-tests-select"
              aria-label="Filter by framework"
            >
              <option value="">All</option>
              {(filterOptions.framework || []).map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </label>
          <label>
            Difficulty
            <select
              value={filters.difficulty}
              onChange={(e) => setFilters((f) => ({ ...f, difficulty: e.target.value }))}
              className="rag-tests-select"
              aria-label="Filter by difficulty"
            >
              <option value="">All</option>
              {(filterOptions.difficulty || []).map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
        </div>
      )}

      <Card className="rag-tests-table-wrap" elevation="var(--md-sys-elevation-level1)">
        <table className="rag-tests-table" role="table">
          <thead>
            <tr>
              <th>
                <input
                  type="checkbox"
                  checked={filteredTests.length > 0 && selectedTestIds.size === filteredTests.length}
                  onChange={toggleSelectAll}
                  aria-label="Select all tests"
                />
              </th>
              <th>Test name</th>
              <th>Platform</th>
              <th>Framework</th>
              <th>Difficulty</th>
              <th>Status</th>
              <th>Time (ms)</th>
              <th>Tok/s</th>
              <th>RAG retrieved</th>
              <th>Confidence</th>
              <th>Details</th>
              <th>Run</th>
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row) => {
              const t = row;
              const last = lastResultByTestId[row.id];
              const openDetails = () => setResultDetailModal({ test: t, last });
              return (
                <tr
                  key={t.id}
                  className={`rag-tests-row ${last?.status === 'FAIL' ? 'fail' : ''}`}
                  onClick={(ev) => {
                    if (ev.target.closest('button, a, input, [role="checkbox"]')) return;
                    openDetails();
                  }}
                >
                  <td onClick={(ev) => ev.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selectedTestIds.has(t.id)}
                      onChange={() => toggleSelectTest(t.id)}
                      aria-label={`Select ${t.name}`}
                    />
                  </td>
                  <td>{t.name || t.id}</td>
                  <td>{t.platform || '-'}</td>
                  <td>{t.framework || '-'}</td>
                  <td>{t.difficulty || '-'}</td>
                  <td>
                    {last ? (
                      <span className={`rag-tests-status ${(last.status || '').toLowerCase()}`}>
                        {last.status}
                      </span>
                    ) : (
                      '-'
                    )}
                  </td>
                  <td>{last?.response_time_ms != null ? last.response_time_ms : '-'}</td>
                  <td>
                    {last?.tokens_per_second_generated != null
                      ? Number(last.tokens_per_second_generated).toFixed(2)
                      : '-'}
                  </td>
                  <td>{last ? yesNo(ragRetrieved(last)) : '-'}</td>
                  <td>{last?.confidence_label || '-'}</td>
                  <td onClick={(ev) => ev.stopPropagation()}>
                    <button
                      type="button"
                      className="coreui-btn coreui-btn-primary coreui-btn-small"
                      onClick={openDetails}
                      aria-label={`Details for ${t.name || t.id}`}
                    >
                      Details
                    </button>
                  </td>
                  <td onClick={(ev) => ev.stopPropagation()} className="rag-tests-actions-cell">
                    <button
                      type="button"
                      className="rag-tests-btn small rag-tests-run-one"
                      disabled={running || !canRun}
                      onClick={() => handleRunSingle(t.id)}
                      aria-label={`Run test ${t.name || t.id}`}
                    >
                      Run
                    </button>
                    <button
                      type="button"
                      className="rag-tests-btn small"
                      disabled={running}
                      onClick={() => handleEditClick(t.id)}
                      aria-label={`Edit ${t.name || t.id}`}
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="rag-tests-btn small rag-tests-delete-btn"
                      disabled={running}
                      onClick={() => handleDeleteClick(t.id)}
                      aria-label={`Delete ${t.name || t.id}`}
                    >
                      Delete
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </Card>

      {failResults.length > 0 && (
        <div className="rag-tests-fail-drilldown">
          <button
            type="button"
            className="rag-tests-history-toggle"
            onClick={() => setShowFailDrilldown((v) => !v)}
            aria-expanded={showFailDrilldown}
          >
            {showFailDrilldown ? '[-]' : '[+]'} Fail drill-down ({failResults.length})
          </button>
          {showFailDrilldown && (
            <div className="rag-tests-fail-panel">
              <div className="rag-tests-fail-filters">
                <label>
                  Domain
                  <select
                    value={failFilters.domain}
                    onChange={(e) => setFailFilters((f) => ({ ...f, domain: e.target.value }))}
                    className="rag-tests-select"
                    aria-label="Filter failed tests by domain"
                  >
                    <option value="">All</option>
                    <option value="SwiftUI">SwiftUI</option>
                    <option value="UIKit">UIKit</option>
                    <option value="Swift">Swift</option>
                  </select>
                </label>
                <label>
                  Difficulty
                  <select
                    value={failFilters.difficulty}
                    onChange={(e) => setFailFilters((f) => ({ ...f, difficulty: e.target.value }))}
                    className="rag-tests-select"
                    aria-label="Filter failed tests by difficulty"
                  >
                    <option value="">All</option>
                    <option value="beginner">beginner</option>
                    <option value="intermediate">intermediate</option>
                    <option value="advanced">advanced</option>
                  </select>
                </label>
                <label>
                  RAG retrieved
                  <select
                    value={failFilters.ragUsed}
                    onChange={(e) => setFailFilters((f) => ({ ...f, ragUsed: e.target.value }))}
                    className="rag-tests-select"
                    aria-label="Filter failed tests by RAG retrieval"
                  >
                    <option value="">All</option>
                    <option value="yes">Only retrieval_used = true</option>
                    <option value="no">Only retrieval_used = false</option>
                  </select>
                </label>
                <label className="rag-tests-checkbox-label">
                  <input
                    type="checkbox"
                    checked={failFilters.ragStrictOnly}
                    onChange={(e) => setFailFilters((f) => ({ ...f, ragStrictOnly: e.target.checked }))}
                  />
                  Only RAG Strict tests
                </label>
              </div>
              <table className="rag-tests-table rag-tests-fail-table" role="table">
                <thead>
                  <tr>
                    <th>Test</th>
                    <th>Platform</th>
                    <th>Framework</th>
                    <th>Difficulty</th>
                    <th>RAG retrieved</th>
                    <th>Grounding</th>
                    <th>Strict quote</th>
                    <th>Confidence</th>
                    <th>Missing concepts</th>
                    <th>Failure reason</th>
                  </tr>
                </thead>
                <tbody>
                  {failResults
                    .filter((r) => {
                      const framework = (r.framework || '').toLowerCase();
                      const difficulty = (r.difficulty || '').toLowerCase();
                      const retrieved = ragRetrieved(r);
                      const ragStrict = !!r.strict_mode || r.strict_rag_ok != null;
                      if (failFilters.domain === 'SwiftUI' && framework !== 'swiftui') return false;
                      if (failFilters.domain === 'UIKit' && framework !== 'uikit') return false;
                      if (failFilters.domain === 'Swift' && framework && framework !== 'swift' && framework !== 'swiftui' && framework !== 'uikit') return false;
                      if (failFilters.difficulty && difficulty !== failFilters.difficulty) return false;
                      if (failFilters.ragUsed === 'yes' && !retrieved) return false;
                      if (failFilters.ragUsed === 'no' && retrieved) return false;
                      if (failFilters.ragStrictOnly && !ragStrict) return false;
                      return true;
                    })
                    .map((r) => (
                      <tr key={`${r.test_id}-${r.model}`}>
                        <td>{r.test_name || r.test_id}</td>
                        <td>{r.platform || '-'}</td>
                        <td>{r.framework || '-'}</td>
                        <td>{r.difficulty || '-'}</td>
                        <td>{yesNo(ragRetrieved(r))}</td>
                        <td>{yesNo(r.grounding_overlap)}</td>
                        <td>{yesNo(r.strict_quote_ok)}</td>
                        <td>{r.confidence_label || '-'}</td>
                        <td>{(r.missing_concepts || []).join(', ') || 'none'}</td>
                        <td>{r.failure_reason || '-'}</td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {filteredTests.length === 0 && !error && !runError && (
        <p className="rag-tests-empty">No tests found. Create one or add .md files under rag_tests/.</p>
      )}

    </>
  );
}
