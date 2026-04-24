import { useCallback, useEffect, useMemo, useState } from 'react';
import Card from './Card';
import CoreUIButton from './CoreUIButton';
import EmptyState from './EmptyState';
import {
  cancelRagTesterV2Run,
  getRagCollections,
  getRagTesterV2RunStatus,
  getRagTests,
  runRagTesterV2,
} from '../services/api';
import '../styles/components/CoreUIButtons.css';
import '../styles/components/RagTestsTab.css';
import '../styles/components/RagTesterV2Tab.css';

const LAST_USED_KEY = 'coreui.rag_tester_v2.last_used.v1';

function loadLastUsed() {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(LAST_USED_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function saveLastUsed(value) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LAST_USED_KEY, JSON.stringify(value || {}));
  } catch {
    // ignore
  }
}

function truncate(text, max = 140) {
  const s = String(text || '').trim();
  if (s.length <= max) return s;
  return `${s.slice(0, max - 1)}...`;
}

function fmtMs(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return `${Math.round(n)} ms`;
}

function fmtNum(value, digits = 2) {
  const n = Number(value);
  if (!Number.isFinite(n)) return '-';
  return n.toFixed(digits);
}

function statusClass(status) {
  const s = String(status || '').toLowerCase();
  if (s === 'retrieved') return 'pass';
  if (s === 'empty' || s === 'skipped' || s === 'error') return 'fail';
  return '';
}

export default function RagTesterV2Tab() {
  const lastUsed = loadLastUsed();
  const [tests, setTests] = useState([]);
  const [filters, setFilters] = useState({ platform: '', framework: '', difficulty: '' });
  const [filterOptions, setFilterOptions] = useState({ platform: [], framework: [], difficulty: [] });
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState(String(lastUsed.collection_name || ''));
  const [runTopK, setRunTopK] = useState(
    Number.isFinite(Number(lastUsed.top_k)) ? Math.max(1, Math.round(Number(lastUsed.top_k))) : 8
  );
  const [runConcurrency, setRunConcurrency] = useState(
    Number.isFinite(Number(lastUsed.concurrency)) ? Math.max(1, Math.round(Number(lastUsed.concurrency))) : 1
  );
  const [disableRerank, setDisableRerank] = useState(Boolean(lastUsed.testing_disable_rerank));
  const [selectedTestIds, setSelectedTestIds] = useState(new Set());
  const [error, setError] = useState(null);
  const [runJobId, setRunJobId] = useState(null);
  const [running, setRunning] = useState(false);
  const [runProgress, setRunProgress] = useState(null);
  const [results, setResults] = useState([]);
  const [detailRow, setDetailRow] = useState(null);

  const loadCollections = useCallback(async () => {
    try {
      const data = await getRagCollections();
      const list = data.collections || [];
      setCollections(list);
      setSelectedCollection((prev) => {
        if (list.length === 0) return '';
        if (prev && list.some((c) => c.name === prev)) return prev;
        return list[0].name;
      });
    } catch {
      setCollections([]);
      setSelectedCollection('');
    }
  }, []);

  const loadTests = useCallback(async () => {
    setError(null);
    try {
      const params = {};
      if (filters.platform) params.platform = filters.platform;
      if (filters.framework) params.framework = filters.framework;
      if (filters.difficulty) params.difficulty = filters.difficulty;
      const data = await getRagTests(params);
      setTests(data.tests || []);
      setFilterOptions(data.filters || { platform: [], framework: [], difficulty: [] });
    } catch (e) {
      setError(String(e?.message || e));
    }
  }, [filters]);

  useEffect(() => {
    void loadCollections();
  }, [loadCollections]);

  useEffect(() => {
    void loadTests();
  }, [loadTests]);

  useEffect(() => {
    setSelectedTestIds((prev) => {
      if (!prev.size) return prev;
      const allowed = new Set((tests || []).map((test) => test.id));
      const next = new Set(Array.from(prev).filter((id) => allowed.has(id)));
      return next.size === prev.size ? prev : next;
    });
  }, [tests]);

  useEffect(() => {
    saveLastUsed({
      collection_name: selectedCollection || '',
      top_k: runTopK,
      concurrency: runConcurrency,
      testing_disable_rerank: disableRerank,
    });
  }, [selectedCollection, runTopK, runConcurrency, disableRerank]);

  useEffect(() => {
    if (!runJobId || !running) return undefined;
    let cancelled = false;
    let timeoutId;

    const poll = async () => {
      try {
        const data = await getRagTesterV2RunStatus(runJobId);
        if (cancelled) return;
        setRunProgress(data.progress || null);
        setResults(Array.isArray(data.results) ? data.results : []);
        if (data.status === 'completed' || data.status === 'cancelled') {
          setRunning(false);
          setRunJobId(null);
          if (data.error) setError(data.error);
          return;
        }
      } catch (e) {
        if (!cancelled) setError(String(e?.message || e));
      }
      if (!cancelled) {
        timeoutId = window.setTimeout(poll, 500);
      }
    };

    timeoutId = window.setTimeout(poll, 300);
    return () => {
      cancelled = true;
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [runJobId, running]);

  const resultByTestId = useMemo(() => {
    const map = new Map();
    for (const row of results || []) {
      if (row?.test_id) map.set(row.test_id, row);
    }
    return map;
  }, [results]);

  const summary = useMemo(() => {
    const total = results.length;
    const retrieved = results.filter((r) => r?.status === 'retrieved').length;
    const empty = results.filter((r) => r?.status === 'empty').length;
    const skipped = results.filter((r) => r?.status === 'skipped').length;
    const errors = results.filter((r) => r?.status === 'error').length;
    const avgLatency = total
      ? results.reduce((sum, r) => sum + Number(r?.latency_ms || 0), 0) / total
      : 0;
    const avgChunks = total
      ? results.reduce((sum, r) => sum + Number(r?.chunks_count || 0), 0) / total
      : 0;
    return { total, retrieved, empty, skipped, errors, avgLatency, avgChunks };
  }, [results]);

  const hasActiveFilters = Boolean(filters.platform || filters.framework || filters.difficulty);
  const hasSelectedTests = selectedTestIds.size > 0;
  const canRun = collections.length > 0 && selectedCollection;

  const runBody = useCallback((opts = {}) => ({
    collection_name: selectedCollection || undefined,
    top_k: Number.isFinite(Number(runTopK)) ? Math.max(1, Math.round(Number(runTopK))) : undefined,
    concurrency: Number(runConcurrency) || 1,
    testing_disable_rerank: Boolean(disableRerank),
    ...opts,
  }), [selectedCollection, runTopK, runConcurrency, disableRerank]);

  const startRun = useCallback(async (body) => {
    setError(null);
    setResults([]);
    setRunProgress(null);
    setDetailRow(null);
    const data = await runRagTesterV2(body);
    setRunJobId(data.job_id);
    setRunning(true);
    setRunProgress({
      current_index: 0,
      total: 0,
      current_test_name: '',
      active_tests: [],
      active_count: 0,
      max_concurrency: Number(runConcurrency) || 1,
      retrieved: 0,
      empty: 0,
      skipped: 0,
      errors: 0,
      pending: 0,
    });
  }, [runConcurrency]);

  const handleRunAll = async () => {
    if (!canRun) {
      setError('Select a Qdrant collection first');
      return;
    }
    await startRun(runBody());
  };

  const handleRunFiltered = async () => {
    if (!canRun) {
      setError('Select a Qdrant collection first');
      return;
    }
    if (!hasActiveFilters) {
      setError('Choose at least one filter first');
      return;
    }
    await startRun(runBody({
      filter: {
        platform: filters.platform || undefined,
        framework: filters.framework || undefined,
        difficulty: filters.difficulty || undefined,
      },
    }));
  };

  const handleRunSelected = async () => {
    if (!canRun) {
      setError('Select a Qdrant collection first');
      return;
    }
    if (!selectedTestIds.size) {
      setError('Select at least one test');
      return;
    }
    await startRun(runBody({ test_ids: Array.from(selectedTestIds) }));
  };

  const handleCancelRun = async () => {
    if (!runJobId) return;
    try {
      await cancelRagTesterV2Run(runJobId);
    } catch (e) {
      setError(String(e?.message || e));
    }
  };

  const toggleSelectedTest = (testId) => {
    setSelectedTestIds((prev) => {
      const next = new Set(prev);
      if (next.has(testId)) next.delete(testId);
      else next.add(testId);
      return next;
    });
  };

  return (
    <div className="rag-tests-tab rag-tester-v2-tab">
      <div className="rag-tests-header">
        <div>
          <h2>Rag Tester V2</h2>
          <p className="rag-tester-v2-subtitle">
            Retrieval-only inspector over the existing <code>rag_tests</code> corpus. No model answer generation.
          </p>
        </div>
      </div>

      <div className="rag-tests-actions">
        <div className="rag-tests-run-controls">
          <Card className="rag-tests-control-card rag-tests-control-card-wide">
            <div className="rag-tests-control-card-copy">
              <h3>Retrieval run</h3>
              <p>Use the same retrieval path as current RAG tests, but inspect the retrieval query, timings, trace steps, and chunks only.</p>
            </div>
            <div className="rag-tests-control-grid">
              <label className="rag-tests-model-label">
                Collection
                <select
                  value={selectedCollection}
                  onChange={(e) => setSelectedCollection(e.target.value)}
                  disabled={collections.length === 0}
                  className="rag-tests-select"
                  aria-label="Select Qdrant collection"
                >
                  {collections.length === 0 ? (
                    <option value="">-- No collections --</option>
                  ) : (
                    collections.map((col) => (
                      <option key={col.name} value={col.name}>
                        {col.name} ({(col.points_count ?? 0)} vectors)
                      </option>
                    ))
                  )}
                </select>
              </label>
              <label className="rag-tests-model-label">
                Top K
                <input
                  type="number"
                  min="1"
                  max="64"
                  step="1"
                  value={runTopK}
                  onChange={(e) => setRunTopK(Math.max(1, Number(e.target.value) || 1))}
                  className="rag-tests-input"
                />
              </label>
              <label className="rag-tests-model-label rag-tests-concurrency-label">
                Parallel tests
                <select
                  value={runConcurrency}
                  onChange={(e) => setRunConcurrency(Number(e.target.value) || 1)}
                  className="rag-tests-select rag-tests-concurrency-select"
                >
                  {[1, 2, 3, 4, 5, 6].map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                </select>
              </label>
              <label className="rag-tests-checkbox-label rag-tester-v2-checkbox">
                <input
                  type="checkbox"
                  checked={disableRerank}
                  onChange={(e) => setDisableRerank(e.target.checked)}
                />
                Disable rerank for this run
              </label>
            </div>
            {collections.length === 0 && (
              <span className="rag-tests-no-collections-hint">
                No collections. Create one in Crawler / RAG then come back.
              </span>
            )}
          </Card>

          <div className="rag-tests-run-actions">
            <CoreUIButton
              variant="primary"
              onClick={handleRunAll}
              disabled={running || !canRun || hasSelectedTests || hasActiveFilters}
            >
              Run all
            </CoreUIButton>
            <CoreUIButton
              onClick={handleRunFiltered}
              disabled={running || !canRun || hasSelectedTests || !hasActiveFilters}
            >
              Run filtered
            </CoreUIButton>
            <CoreUIButton
              onClick={handleRunSelected}
              disabled={running || !canRun || !hasSelectedTests}
            >
              Run selected
            </CoreUIButton>
          </div>
        </div>
      </div>

      {running && runProgress && (
        <Card className="rag-tests-progress-panel" role="status" aria-live="polite">
          <div className="rag-tests-progress-header">
            <span className="rag-tests-progress-spinner" aria-hidden="true" />
            <span className="rag-tests-progress-title">Running retrieval inspection</span>
            <span className="rag-tests-progress-count">
              [{runProgress.current_index || 0}/{runProgress.total || 0}]
            </span>
            <CoreUIButton
              size="sm"
              onClick={handleCancelRun}
            >
              Cancel
            </CoreUIButton>
          </div>
          <p className="rag-tests-progress-current">
            <span className="rag-tests-progress-current-label">Current test:</span>{' '}
            <strong>{runProgress.current_test_name || '-'}</strong>
          </p>
          <div className="rag-tests-progress-stats">
            <span className="rag-tests-progress-stat passed">
              <span className="rag-tests-progress-stat-value">{runProgress.retrieved ?? 0}</span>
              <span className="rag-tests-progress-stat-label">retrieved</span>
            </span>
            <span className="rag-tests-progress-stat">
              <span className="rag-tests-progress-stat-value">{runProgress.empty ?? 0}</span>
              <span className="rag-tests-progress-stat-label">empty</span>
            </span>
            <span className="rag-tests-progress-stat">
              <span className="rag-tests-progress-stat-value">{runProgress.skipped ?? 0}</span>
              <span className="rag-tests-progress-stat-label">skipped</span>
            </span>
            <span className="rag-tests-progress-stat failed">
              <span className="rag-tests-progress-stat-value">{runProgress.errors ?? 0}</span>
              <span className="rag-tests-progress-stat-label">errors</span>
            </span>
          </div>
          <div className="rag-tests-progress-bar-wrap" aria-hidden="true">
            <div
              className="rag-tests-progress-bar-fill"
              style={{
                width: runProgress.total
                  ? `${Math.round(((runProgress.current_index || 0) / runProgress.total) * 100)}%`
                  : '0%',
              }}
            />
          </div>
        </Card>
      )}

      {(error || null) && (
        <div className="rag-tests-error" role="alert">
          {error}
        </div>
      )}

      {results.length > 0 && (
        <section className="rag-tests-run-summary">
          <div className="rag-tests-summary-kpis">
            <div className="rag-tests-summary-kpi"><strong>Total:</strong> {summary.total}</div>
            <div className="rag-tests-summary-kpi"><strong>Retrieved:</strong> {summary.retrieved}</div>
            <div className="rag-tests-summary-kpi"><strong>Empty:</strong> {summary.empty}</div>
            <div className="rag-tests-summary-kpi"><strong>Skipped:</strong> {summary.skipped}</div>
            <div className="rag-tests-summary-kpi"><strong>Errors:</strong> {summary.errors}</div>
            <div className="rag-tests-summary-kpi"><strong>Avg latency:</strong> {fmtMs(summary.avgLatency)}</div>
            <div className="rag-tests-summary-kpi"><strong>Avg chunks:</strong> {fmtNum(summary.avgChunks, 1)}</div>
          </div>
        </section>
      )}

      {!running && results.length === 0 && (
        <EmptyState>
          Run a retrieval inspection to review the effective query, pipeline timings, trace steps, and retrieved chunks.
        </EmptyState>
      )}

      <div className="rag-tests-filters">
        <label>
          Platform
          <select
            value={filters.platform}
            onChange={(e) => setFilters((prev) => ({ ...prev, platform: e.target.value }))}
            className="rag-tests-select"
          >
            <option value="">All</option>
            {(filterOptions.platform || []).map((x) => (
              <option key={x} value={x}>{x}</option>
            ))}
          </select>
        </label>
        <label>
          Framework
          <select
            value={filters.framework}
            onChange={(e) => setFilters((prev) => ({ ...prev, framework: e.target.value }))}
            className="rag-tests-select"
          >
            <option value="">All</option>
            {(filterOptions.framework || []).map((x) => (
              <option key={x} value={x}>{x}</option>
            ))}
          </select>
        </label>
        <label>
          Difficulty
          <select
            value={filters.difficulty}
            onChange={(e) => setFilters((prev) => ({ ...prev, difficulty: e.target.value }))}
            className="rag-tests-select"
          >
            <option value="">All</option>
            {(filterOptions.difficulty || []).map((x) => (
              <option key={x} value={x}>{x}</option>
            ))}
          </select>
        </label>
      </div>

      {!tests.length ? (
        <EmptyState>No tests found for the current filters.</EmptyState>
      ) : (
        <Card className="rag-tests-table-wrap" elevation="var(--md-sys-elevation-level1)">
          <table className="rag-tests-table" role="table">
            <thead>
              <tr>
                <th>Sel</th>
                <th>Test</th>
                <th>Status</th>
                <th>Chunks</th>
                <th>Latency</th>
                <th>Retrieval query</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {tests.map((test) => {
                const row = resultByTestId.get(test.id);
                const checked = selectedTestIds.has(test.id);
                return (
                  <tr
                    key={test.id}
                    className={`rag-tests-row ${row?.status === 'error' ? 'fail' : ''}`}
                    onClick={() => row && setDetailRow(row)}
                  >
                    <td onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => toggleSelectedTest(test.id)}
                        aria-label={`Select ${test.name || test.id}`}
                      />
                    </td>
                    <td>
                      <div>{test.name || test.id}</div>
                      <div className="rag-tests-detail-metrics">{truncate(test.question, 90)}</div>
                    </td>
                    <td>
                      {row ? (
                        <span className={`rag-tests-status ${statusClass(row.status)}`}>
                          {row.status}
                        </span>
                      ) : '-'}
                    </td>
                    <td>{row ? row.chunks_count ?? 0 : '-'}</td>
                    <td>{row ? fmtMs(row.latency_ms) : '-'}</td>
                    <td className="rag-tester-v2-query-cell">{row ? truncate(row.retrieval_query, 100) : '-'}</td>
                    <td onClick={(e) => e.stopPropagation()}>
                      <CoreUIButton
                        size="sm"
                        onClick={() => row && setDetailRow(row)}
                        disabled={!row}
                      >
                        View
                      </CoreUIButton>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>
      )}

      {detailRow && (
        <div
          className="rag-tests-modal rag-tests-result-modal"
          role="dialog"
          aria-modal="true"
          aria-labelledby="rag-tester-v2-detail-title"
          onClick={() => setDetailRow(null)}
        >
          <div
            className="rag-tests-modal-content rag-tests-result-modal-content"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="rag-tests-result-modal-header">
              <h3 id="rag-tester-v2-detail-title">{detailRow.test_name || detailRow.test_id}</h3>
              <CoreUIButton
                variant="ghost"
                size="sm"
                onClick={() => setDetailRow(null)}
              >
                Close
              </CoreUIButton>
            </div>
            <p className="rag-tests-result-modal-meta">
              <span className={`rag-tests-status ${statusClass(detailRow.status)}`}>{detailRow.status}</span>
              {' '}| latency {fmtMs(detailRow.latency_ms)} | chunks {detailRow.chunks_count ?? 0}
            </p>

            <section className="rag-tests-result-section">
              <h4>Question</h4>
              <p className="rag-tests-result-question">{detailRow.question}</p>
            </section>

            <section className="rag-tests-result-section">
              <h4>Effective retrieval query</h4>
              <pre className="rag-tests-pre rag-tests-pre-tight">{detailRow.retrieval_query || '-'}</pre>
            </section>

            <section className="rag-tests-result-section">
              <h4>RAG timings</h4>
              {!Object.keys(detailRow.rag_timings || {}).length ? (
                <EmptyState>No timing data.</EmptyState>
              ) : (
                <div className="rag-tests-timing-cards">
                  {Object.entries(detailRow.rag_timings || {}).map(([key, value]) => (
                    <div key={key} className="rag-tests-timing-card">
                      <span className="rag-tests-timing-card-label">{key}</span>
                      <span className="rag-tests-timing-card-value">
                        {typeof value === 'number' ? fmtNum(value, 3) : String(value)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </section>

            <section className="rag-tests-result-section">
              <h4>Trace steps</h4>
              {!detailRow.trace_steps?.length ? (
                <EmptyState>No trace steps captured.</EmptyState>
              ) : (
                <ul className="rag-tests-rag-query-list">
                  {detailRow.trace_steps.map((step, index) => (
                    <li key={`trace-${index}`}>
                      <span className="rag-tests-rag-query-meta">
                        {step.label || step.name || step.id || `step-${index + 1}`}
                      </span>
                      <p className="rag-tests-detail-metrics">
                        {step.detail || step.description || step.status || '-'}
                      </p>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <section className="rag-tests-result-section">
              <h4>Retrieved chunks</h4>
              {!detailRow.chunks_info?.length ? (
                <EmptyState>No chunks in this retrieval result.</EmptyState>
              ) : (
                <ul className="rag-tests-chunks rag-tests-chunks-modal">
                  {detailRow.chunks_info.map((chunk, index) => (
                    <li key={`chunk-${index}`}>
                      <span className="rag-tests-chunk-meta">
                        #{index + 1} | score {fmtNum(chunk.score ?? chunk.rerank_score ?? 0, 3)} | {chunk.section_path_joined || chunk.source_name || chunk.url || '-'}
                      </span>
                      <pre className="rag-tests-pre small">{chunk.text_preview || chunk.text || chunk.content || '-'}</pre>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            {detailRow.error && (
              <section className="rag-tests-result-section">
                <h4>Error</h4>
                <p className="rag-tests-detail-error">{detailRow.error}</p>
              </section>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
