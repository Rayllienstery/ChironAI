import { useState, useEffect, useCallback } from 'react';
import Card from './Card';
import {
  RagResultDetailModal,
  RagTestFormModal,
} from './RagTestsModals';
import {
  getModels,
  getPrompts,
  getRagCollections,
  getRagTests,
  getRagTest,
  getRagTestRuns,
  getRagTestRun,
  getRagTestRunsSummary,
  createRagTest,
  updateRagTest,
  deleteRagTest,
  exportRagTestRun,
} from '../services/api';
import { isLogicalRagModelId } from '../constants/llmProxyModels';
import '../styles/components/RagTestsTab.css';

/** Cloud/metered Ollama tags (e.g. qwen3.5:cloud, ...:397b-cloud) may bill tokens. */
function modelTagLooksCloud(modelId) {
  const s = String(modelId || '').trim().toLowerCase();
  if (!s) return false;
  return s.includes(':cloud') || s.endsWith('-cloud');
}

function confirmCloudRagRun(modelId) {
  if (!modelTagLooksCloud(modelId)) return true;
  return window.confirm(
    'Cloud-tagged model selected: running RAG Tests may consume paid tokens. Continue?'
  );
}

function RagTestsTab({
  runJobId = null,
  running = false,
  runProgress = null,
  results = [],
  runError = null,
  onStartRun,
  onCancelRun,
}) {
  const [models, setModels] = useState([]);
  const [selectedModel, setSelectedModel] = useState('');
  const [tests, setTests] = useState([]);
  const [filters, setFilters] = useState({ platform: '', framework: '', difficulty: '' });
  const [filterOptions, setFilterOptions] = useState({ platform: [], framework: [], difficulty: [] });
  const [error, setError] = useState(null);
  const [resultDetailModal, setResultDetailModal] = useState(null);
  const [selectedTestIds, setSelectedTestIds] = useState(new Set());
  const [createOpen, setCreateOpen] = useState(false);
  const [createForm, setCreateForm] = useState({
    name: '',
    question: '',
    concepts: '',
    platform: 'iOS',
    framework: 'SwiftUI',
    difficulty: 'intermediate',
    concept_mode: 'all',
    rag_strict: false,
    min_os: '',
    notes: '',
  });
  const [createSubmitting, setCreateSubmitting] = useState(false);
  const [createConceptsWarning, setCreateConceptsWarning] = useState('');
  const [editOpen, setEditOpen] = useState(false);
  const [editTestId, setEditTestId] = useState(null);
  const [editForm, setEditForm] = useState({
    name: '',
    question: '',
    concepts: '',
    platform: 'iOS',
    framework: 'SwiftUI',
    difficulty: 'intermediate',
    concept_mode: 'all',
    rag_strict: false,
    min_os: '',
    notes: '',
  });
  const [editSubmitting, setEditSubmitting] = useState(false);
  const [editConceptsWarning, setEditConceptsWarning] = useState('');
  const [runHistory, setRunHistory] = useState([]);
  const [runHistoryLoading, setRunHistoryLoading] = useState(false);
  const [runHistoryLoadingMore, setRunHistoryLoadingMore] = useState(false);
  const [runHistoryHasMore, setRunHistoryHasMore] = useState(true);
  const [historyFilters, setHistoryFilters] = useState({ model: '', from_date: '', to_date: '', status: '' });
  const [runSummary, setRunSummary] = useState(null);
  const [selectedRunId, setSelectedRunId] = useState(null);
  const [selectedRunDetail, setSelectedRunDetail] = useState(null);
  const [historySectionOpen, setHistorySectionOpen] = useState(false);
  const [showFailDrilldown, setShowFailDrilldown] = useState(false);
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState('');
  const [prompts, setPrompts] = useState([]);
  const [selectedPromptName, setSelectedPromptName] = useState('');

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

  const loadPrompts = useCallback(async () => {
    try {
      const data = await getPrompts();
      const list = (data.prompts || []).filter(
        (p) => p.name && p.name.toLowerCase() !== 'readme'
      );
      setPrompts(list);
    } catch {
      setPrompts([]);
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const list = await getModels();
      setModels(list || []);
      if (!selectedModel && list?.length) {
        const pick = list.find((m) => m.id && !isLogicalRagModelId(m.id)) || list[0];
        setSelectedModel(pick.id || '');
      }
    } catch (e) {
      setError(e.message);
    }
  }, [selectedModel]);

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
      setError(e.message);
      setTests([]);
    }
  }, [filters.platform, filters.framework, filters.difficulty]);

  useEffect(() => {
    loadModels();
  }, [loadModels]);

  useEffect(() => {
    loadCollections();
  }, [loadCollections]);

  useEffect(() => {
    loadPrompts();
  }, [loadPrompts]);

  useEffect(() => {
    loadTests();
  }, [loadTests]);

  const HISTORY_PAGE_SIZE = 20;

  const loadRunHistory = useCallback(async (offset = 0) => {
    const isReset = offset === 0;
    if (isReset) {
      setRunHistoryLoading(true);
    } else {
      setRunHistoryLoadingMore(true);
    }
    setError(null);
    try {
      const opts = {
        limit: HISTORY_PAGE_SIZE,
        offset,
        model: historyFilters.model || undefined,
        from_date: historyFilters.from_date || undefined,
        to_date: historyFilters.to_date || undefined,
        status: historyFilters.status || undefined,
      };
      const data = await getRagTestRuns(opts);
      const runs = data.runs || [];
      if (isReset) {
        setRunHistory(runs);
      } else {
        setRunHistory((prev) => [...prev, ...runs]);
      }
      setRunHistoryHasMore(runs.length === HISTORY_PAGE_SIZE);
    } catch (e) {
      setError(e.message);
    } finally {
      setRunHistoryLoading(false);
      setRunHistoryLoadingMore(false);
    }
  }, [historyFilters.model, historyFilters.from_date, historyFilters.to_date, historyFilters.status]);

  useEffect(() => {
    loadRunHistory(0);
  }, [loadRunHistory]);

  const loadRunSummary = useCallback(async () => {
    try {
      const summary = await getRagTestRunsSummary({
        limit: 50,
        model: historyFilters.model || undefined,
        from_date: historyFilters.from_date || undefined,
        to_date: historyFilters.to_date || undefined,
      });
      setRunSummary(summary);
    } catch {
      setRunSummary(null);
    }
  }, [historyFilters.model, historyFilters.from_date, historyFilters.to_date]);

  useEffect(() => {
    if (historySectionOpen) {
      loadRunSummary();
    }
  }, [historySectionOpen, loadRunSummary]);

  useEffect(() => {
    if (!running && runJobId === null) {
      loadRunHistory();
    }
  }, [running, runJobId, loadRunHistory]);

  useEffect(() => {
    if (!resultDetailModal) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setResultDetailModal(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [resultDetailModal]);

  const handleSelectPastRun = async (runId) => {
    setError(null);
    try {
      const run = await getRagTestRun(runId);
      setSelectedRunId(runId);
      setSelectedRunDetail(run);
      setResultDetailModal(null);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleBackToCurrent = () => {
    setSelectedRunId(null);
    setSelectedRunDetail(null);
    setResultDetailModal(null);
  };

  const filteredTests = tests;

  const runBody = (opts = {}) => ({
    model: selectedModel,
    collection_name: selectedCollection || undefined,
    prompt_name: selectedPromptName || undefined,
    ...opts,
  });

  const canRun = collections.length > 0 && selectedCollection;

  const handleRunAll = async () => {
    if (!selectedModel) {
      setError('Select a model first');
      return;
    }
    if (!canRun) {
      setError('Select a Qdrant collection first');
      return;
    }
    if (!confirmCloudRagRun(selectedModel)) return;
    setError(null);
    try {
      await onStartRun(runBody({ filter: filters.platform || filters.framework || filters.difficulty ? filters : undefined }));
    } catch (e) {
      setError(e.message);
    }
  };

  const handleRunFiltered = async () => {
    if (!selectedModel) {
      setError('Select a model first');
      return;
    }
    if (!canRun) {
      setError('Select a Qdrant collection first');
      return;
    }
    if (!confirmCloudRagRun(selectedModel)) return;
    setError(null);
    try {
      await onStartRun(runBody({
        filter: {
          platform: filters.platform || undefined,
          framework: filters.framework || undefined,
          difficulty: filters.difficulty || undefined,
        },
      }));
    } catch (e) {
      setError(e.message);
    }
  };

  const handleRunSelected = async () => {
    if (!selectedModel) {
      setError('Select a model first');
      return;
    }
    if (!canRun) {
      setError('Select a Qdrant collection first');
      return;
    }
    if (selectedTestIds.size === 0) {
      setError('Select at least one test');
      return;
    }
    if (!confirmCloudRagRun(selectedModel)) return;
    setError(null);
    try {
      await onStartRun(runBody({ test_ids: Array.from(selectedTestIds) }));
    } catch (e) {
      setError(e.message);
    }
  };

  const handleRunSingle = async (testId) => {
    if (!selectedModel) {
      setError('Select a model first');
      return;
    }
    if (!canRun) {
      setError('Select a Qdrant collection first');
      return;
    }
    if (!confirmCloudRagRun(selectedModel)) return;
    setError(null);
    try {
      await onStartRun(runBody({ test_ids: [testId] }));
    } catch (e) {
      setError(e.message);
    }
  };

  const handleCancelRun = async () => {
    if (!runJobId) return;
    try {
      await onCancelRun();
    } catch (e) {
      setError(e.message);
    }
  };

  const toggleSelectTest = (id) => {
    setSelectedTestIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedTestIds.size === filteredTests.length) {
      setSelectedTestIds(new Set());
    } else {
      setSelectedTestIds(new Set(filteredTests.map((t) => t.id)));
    }
  };

  const validateConceptLines = (text) => {
    const lines = (text || '')
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    const problematic = lines.filter((line) => {
      const lowered = line.toLowerCase();
      return (
        lowered.includes('/') ||
        lowered.includes(',') ||
        lowered.includes(';') ||
        lowered.includes(' and ')
      );
    });
    if (problematic.length === 0) {
      return '';
    }
    if (problematic.length === 1) {
      return `Entry "${problematic[0]}" looks like multiple concepts; use one concept per line (for example: "weak" and "unowned" on separate lines).`;
    }
    return 'Some Expected Concepts entries look like multiple concepts; please use one concept per line.';
  };

  const handleCreateSubmit = async (e) => {
    e.preventDefault();
    const warning = validateConceptLines(createForm.concepts);
    setCreateConceptsWarning(warning);
    const concepts = createForm.concepts
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    setCreateSubmitting(true);
    setError(null);
    try {
      await createRagTest({
        name: createForm.name || createForm.question.slice(0, 80),
        question: createForm.question,
        concepts,
        platform: createForm.platform,
        framework: createForm.framework,
        difficulty: createForm.difficulty,
        concept_mode: createForm.concept_mode,
        rag_strict: createForm.rag_strict,
        min_os: createForm.min_os || undefined,
        notes: createForm.notes || undefined,
      });
      setCreateOpen(false);
      setCreateForm({
        name: '',
        question: '',
        concepts: '',
        platform: 'iOS',
        framework: 'SwiftUI',
        difficulty: 'intermediate',
        concept_mode: 'all',
        rag_strict: false,
        min_os: '',
        notes: '',
      });
      loadTests();
    } catch (e) {
      setError(e.message);
    } finally {
      setCreateSubmitting(false);
    }
  };

  const handleEditClick = async (testId) => {
    setError(null);
    try {
      const test = await getRagTest(testId);
      setEditTestId(testId);
      setEditForm({
        name: test.name || '',
        question: test.question || '',
        concepts: (test.expected_concepts || []).join('\n'),
        platform: test.platform || 'iOS',
        framework: test.framework || 'SwiftUI',
        difficulty: test.difficulty || 'intermediate',
        concept_mode: test.concept_mode || 'all',
        rag_strict: Boolean(test.rag_strict),
        min_os: test.min_os || '',
        notes: test.notes || '',
      });
      setEditOpen(true);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleEditSubmit = async (e) => {
    e.preventDefault();
    const warning = validateConceptLines(editForm.concepts);
    setEditConceptsWarning(warning);
    const concepts = editForm.concepts
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    setEditSubmitting(true);
    setError(null);
    try {
      await updateRagTest(editTestId, {
        name: editForm.name || editForm.question.slice(0, 80),
        question: editForm.question,
        concepts,
        platform: editForm.platform,
        framework: editForm.framework,
        difficulty: editForm.difficulty,
        concept_mode: editForm.concept_mode,
        rag_strict: editForm.rag_strict,
        min_os: editForm.min_os || undefined,
        notes: editForm.notes || undefined,
      });
      setEditOpen(false);
      setEditTestId(null);
      loadTests();
    } catch (e) {
      setError(e.message);
    } finally {
      setEditSubmitting(false);
    }
  };

  const handleDeleteClick = async (testId) => {
    if (!window.confirm('Delete this test? This cannot be undone.')) return;
    setError(null);
    try {
      await deleteRagTest(testId);
      loadTests();
      if (selectedRunDetail?.results?.some((r) => r.test_id === testId)) {
        setSelectedRunId(null);
        setSelectedRunDetail(null);
        setResultDetailModal(null);
      }
    } catch (e) {
      setError(e.message);
    }
  };

  const displayResults = selectedRunDetail?.results ?? results;
  const lastResultByTestId = displayResults.length
    ? displayResults.reduce((acc, r) => {
        acc[r.test_id] = r;
        return acc;
      }, {})
    : {};
  const isViewingPastRun = Boolean(selectedRunDetail);
  const failResults = (displayResults || []).filter((r) => r.status === 'FAIL');

  const [failFilters, setFailFilters] = useState({
    domain: '',
    difficulty: '',
    ragUsed: '',
    ragStrictOnly: false,
  });

  const tableRows = isViewingPastRun
    ? displayResults
    : filteredTests;
  const formatRunDate = (iso) => {
    if (!iso) return '-';
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
    } catch {
      return iso;
    }
  };

  return (
    <div className="rag-tests-tab">
      <div className="rag-tests-header">
        <h2>RAG Tests</h2>
        <div className="rag-tests-actions">
          <label className="rag-tests-model-label">
            Model
            <select
              value={selectedModel}
              onChange={(e) => setSelectedModel(e.target.value)}
              disabled={running}
              className="rag-tests-select"
              aria-label="Select model"
            >
              {models.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.name || m.id}
                </option>
              ))}
            </select>
          </label>
          <label className="rag-tests-model-label">
            Collection
            <select
              value={selectedCollection}
              onChange={(e) => setSelectedCollection(e.target.value)}
              disabled={running || collections.length === 0}
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
            Prompt template
            <select
              value={selectedPromptName}
              onChange={(e) => setSelectedPromptName(e.target.value)}
              disabled={running}
              className="rag-tests-select"
              aria-label="Select prompt template"
            >
              <option value="">-- Default --</option>
              {prompts.map((p) => (
                <option key={p.id || p.name} value={p.name}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          {collections.length === 0 && (
            <span className="rag-tests-no-collections-hint">
              No collections. Create one in Crawler / RAG then come back.
            </span>
          )}
          <button
            type="button"
            className="rag-tests-btn primary"
            onClick={handleRunAll}
            disabled={running || !selectedModel || !canRun}
          >
            Run all
          </button>
          <button
            type="button"
            className="rag-tests-btn"
            onClick={handleRunFiltered}
            disabled={running || !selectedModel || !canRun}
          >
            Run filtered
          </button>
          <button
            type="button"
            className="rag-tests-btn"
            onClick={handleRunSelected}
            disabled={running || !selectedModel || !canRun || selectedTestIds.size === 0}
          >
            Run selected
          </button>
          <button
            type="button"
            className="rag-tests-btn"
            onClick={() => setCreateOpen(true)}
            disabled={running}
          >
            Create test
          </button>
        </div>
      </div>

      {running && runProgress && (
        <Card className="rag-tests-progress-panel" role="status" aria-live="polite">
          <div className="rag-tests-progress-header">
            <span className="rag-tests-progress-spinner" aria-hidden="true" />
            <span className="rag-tests-progress-title">Running tests</span>
            <span className="rag-tests-progress-count">
              [{runProgress.current_index || 0}/{runProgress.total || 0}]
            </span>
            <button
              type="button"
              className="rag-tests-btn rag-tests-cancel-btn"
              onClick={handleCancelRun}
              aria-label="Cancel run"
            >
              Cancel
            </button>
          </div>
          <p className="rag-tests-progress-current">
            <span className="rag-tests-progress-current-label">Current test:</span>{' '}
            <strong>{runProgress.current_test_name || '-'}</strong>
          </p>
          <div className="rag-tests-progress-stats">
            <span className="rag-tests-progress-stat passed">
              <span className="rag-tests-progress-stat-value">{runProgress.passed ?? 0}</span>
              <span className="rag-tests-progress-stat-label">passed</span>
            </span>
            <span className="rag-tests-progress-stat failed">
              <span className="rag-tests-progress-stat-value">{runProgress.failed ?? 0}</span>
              <span className="rag-tests-progress-stat-label">failed</span>
            </span>
            <span className="rag-tests-progress-stat pending">
              <span className="rag-tests-progress-stat-value">{runProgress.pending ?? 0}</span>
              <span className="rag-tests-progress-stat-label">pending</span>
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
      {(error || runError) && (
        <div className="rag-tests-error" role="alert">
          {error || runError}
        </div>
      )}

      {isViewingPastRun && selectedRunDetail && (
        <div className="rag-tests-past-run-banner">
          <span className="rag-tests-past-run-label">
            Viewing run from {formatRunDate(selectedRunDetail.created_at)} - Model: {selectedRunDetail.model} - Passed: {selectedRunDetail.passed}, Failed: {selectedRunDetail.failed}
          </span>
          <div className="rag-tests-past-run-actions">
            <button
              type="button"
              className="rag-tests-btn small"
              onClick={() => exportRagTestRun(selectedRunId, 'json')}
              aria-label="Export run as JSON"
            >
              Export JSON
            </button>
            <button
              type="button"
              className="rag-tests-btn small"
              onClick={() => exportRagTestRun(selectedRunId, 'csv')}
              aria-label="Export run as CSV"
            >
              Export CSV
            </button>
            <button type="button" className="rag-tests-btn" onClick={handleBackToCurrent}>
              Back to current
            </button>
          </div>
        </div>
      )}

      <div className="rag-tests-history-section">
        <button
          type="button"
          className="rag-tests-history-toggle"
          onClick={() => setHistorySectionOpen((o) => !o)}
          aria-expanded={historySectionOpen}
        >
          {historySectionOpen ? '[-]' : '[+]'} Run history
        </button>
        {historySectionOpen && (
          <div className="rag-tests-history-panel">
            {runSummary && (
              <div className="rag-tests-summary-block">
                <p className="rag-tests-summary-line">
                  Last {runSummary.total_runs} runs: {runSummary.total_tests} total tests, {runSummary.pass_rate_pct}% pass rate
                </p>
                {runSummary.per_model?.length > 0 && (
                  <p className="rag-tests-summary-line">
                    By model: {runSummary.per_model.map((m) => `${m.model} ${m.pass_rate_pct}%`).join(', ')}
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
            {runHistoryLoading ? (
              <p className="rag-tests-history-loading">Loading history...</p>
            ) : runHistory.length === 0 ? (
              <p className="rag-tests-history-empty">No past runs yet.</p>
            ) : (
              <>
              <table className="rag-tests-history-table" role="table">
                <thead>
                  <tr>
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
                    <tr key={run.id} className="rag-tests-history-row">
                      <td>{formatRunDate(run.created_at)}</td>
                      <td>{run.model}</td>
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
        )}
      </div>

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

      <Card className="rag-tests-table-wrap" elevation="var(--md-sys-elevation-level1)">
        <table className="rag-tests-table" role="table">
          <thead>
            <tr>
              {!isViewingPastRun && (
                <th>
                  <input
                    type="checkbox"
                    checked={filteredTests.length > 0 && selectedTestIds.size === filteredTests.length}
                    onChange={toggleSelectAll}
                    aria-label="Select all tests"
                  />
                </th>
              )}
              <th>Test name</th>
              <th>Platform</th>
              <th>Framework</th>
              {!isViewingPastRun && <th>Difficulty</th>}
              <th>Status</th>
              <th>Time (ms)</th>
              <th>RAG</th>
              <th>Confidence</th>
              <th>Details</th>
              {!isViewingPastRun && <th>Run</th>}
            </tr>
          </thead>
          <tbody>
            {tableRows.map((row) => {
              const t = isViewingPastRun
                ? { id: row.test_id, name: row.test_name, platform: row.platform, framework: row.framework, difficulty: '', question: row.question || '' }
                : row;
              const last = isViewingPastRun ? row : lastResultByTestId[row.id];
              const openDetails = () => setResultDetailModal({ test: t, last });
              return (
                <tr
                  key={t.id}
                  className={`rag-tests-row ${last?.status === 'FAIL' ? 'fail' : ''}`}
                  onClick={(ev) => {
                    if (ev.target.closest('button, a, input, [role="checkbox"]')) return;
                    openDetails();
                  }}
                  style={{ cursor: 'pointer' }}
                >
                  {!isViewingPastRun && (
                    <td onClick={(ev) => ev.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selectedTestIds.has(t.id)}
                        onChange={() => toggleSelectTest(t.id)}
                        aria-label={`Select ${t.name}`}
                      />
                    </td>
                  )}
                  <td>{t.name || t.id}</td>
                  <td>{t.platform || '-'}</td>
                  <td>{t.framework || '-'}</td>
                  {!isViewingPastRun && <td>{t.difficulty || '-'}</td>}
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
                  <td>{last ? (last.rag_used ? 'Yes' : 'No') : '-'}</td>
                  <td>{last?.confidence_label || '-'}</td>
                  <td onClick={(ev) => ev.stopPropagation()}>
                    <button
                      type="button"
                      className="rag-tests-btn small"
                      onClick={openDetails}
                      aria-label={`Details for ${t.name || t.id}`}
                    >
                      Details
                    </button>
                  </td>
                  {!isViewingPastRun && (
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
                  )}
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
                  RAG used
                  <select
                    value={failFilters.ragUsed}
                    onChange={(e) => setFailFilters((f) => ({ ...f, ragUsed: e.target.value }))}
                    className="rag-tests-select"
                    aria-label="Filter failed tests by RAG usage"
                  >
                    <option value="">All</option>
                    <option value="yes">Only rag_used = true</option>
                    <option value="no">Only rag_used = false</option>
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
                    <th>RAG used</th>
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
                      const ragUsed = !!r.rag_used;
                      const ragStrict = !!r.rag_strict;
                      if (failFilters.domain === 'SwiftUI' && framework !== 'swiftui') return false;
                      if (failFilters.domain === 'UIKit' && framework !== 'uikit') return false;
                      if (failFilters.domain === 'Swift' && framework && framework !== 'swift' && framework !== 'swiftui' && framework !== 'uikit') return false;
                      if (failFilters.difficulty && difficulty !== failFilters.difficulty) return false;
                      if (failFilters.ragUsed === 'yes' && !ragUsed) return false;
                      if (failFilters.ragUsed === 'no' && ragUsed) return false;
                      if (failFilters.ragStrictOnly && !ragStrict) return false;
                      return true;
                    })
                    .map((r) => (
                      <tr key={`${r.test_id}-${r.model}`}>
                        <td>{r.test_name || r.test_id}</td>
                        <td>{r.platform || '-'}</td>
                        <td>{r.framework || '-'}</td>
                        <td>{r.difficulty || '-'}</td>
                        <td>{r.rag_used ? 'Yes' : 'No'}</td>
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
    </div>
  );
}

export default RagTestsTab;
