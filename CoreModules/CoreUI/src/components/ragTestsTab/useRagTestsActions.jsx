import { useEffect, useState } from 'react';
import {
  createRagTest,
  deleteRagTest,
  getRagTest,
  updateRagTest,
} from '../../services/api';
import { confirmCloudRagRun } from './helpers';

export function useRagTestsActions(core, {
  runJobId = null,
  running = false,
  runProgress = null,
  results = [],
  runError = null,
  pendingOpenRunId = null,
  onPendingOpenHandled = null,
  onStartRun,
  onCancelRun,
}) {
  const {
    tests, filters, selectedProviderId, selectedModel, selectedCollection,
    selectedPromptName, runTemperature, runTopK, runStrictMode, runConcurrency,
    selectedTestIds, setSelectedTestIds, setError, createForm, setCreateForm,
    setCreateOpen, setCreateSubmitting, setCreateConceptsWarning, editForm, setEditForm,
    setEditOpen, setEditTestId, setEditSubmitting, setEditConceptsWarning, collections,
    loadTests, liveMonitorDetailOpen, setLiveMonitorDetailOpen, liveDetailCardIndex,
    setLiveDetailCardIndex, currentStepStartedAt, liveNowMs, liveTrace, liveSse,
    resultDetailModal, setResultDetailModal, runHistoryModal, setRunHistoryModal,
    historySectionOpen, setHistorySectionOpen, runCompareModal, setRunCompareModal,
  } = core;

  const filteredTests = tests;

  const runBody = (opts = {}) => ({
    provider_id: selectedProviderId,
    model: selectedModel,
    collection_name: selectedCollection || undefined,
    prompt_name: selectedPromptName || undefined,
    temperature: Number.isFinite(runTemperature) ? runTemperature : 0,
    top_k: Number.isFinite(runTopK) && runTopK > 0 ? runTopK : undefined,
    concurrency: Number(runConcurrency) || 1,
    strict_mode: Boolean(runStrictMode),
    ...opts,
  });

  const canRun = collections.length > 0 && selectedCollection;
  const hasActiveFilters = Boolean(filters.platform || filters.framework || filters.difficulty);
  const hasSelectedTests = selectedTestIds.size > 0;
  const baseRunDisabled = !selectedModel || !canRun;
  const runAllDisabled = running || baseRunDisabled || hasSelectedTests || hasActiveFilters;
  const runFilteredDisabled = running || baseRunDisabled || hasSelectedTests || !hasActiveFilters;
  const runSelectedDisabled = running || baseRunDisabled || !hasSelectedTests;

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
      await onStartRun(runBody());
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
    if (!hasActiveFilters) {
      setError('Choose at least one filter first');
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
    } catch (e) {
      setError(e.message);
    }
  };

  const displayResults = results;
  const lastResultByTestId = displayResults.length
    ? displayResults.reduce((acc, r) => {
        acc[r.test_id] = r;
        return acc;
      }, {})
    : {};
  const failResults = (displayResults || []).filter((r) => r.status === 'FAIL');

  const [failFilters, setFailFilters] = useState({
    domain: '',
    difficulty: '',
    ragUsed: '',
    ragStrictOnly: false,
  });

  const tableRows = filteredTests;
  const currentStepElapsedMs = currentStepStartedAt && running
    ? Math.max(0, liveNowMs - currentStepStartedAt)
    : null;
  const activeLiveCards = Array.isArray(runProgress?.active_live)
    ? runProgress.active_live
        .filter((x) => x && typeof x === 'object')
        .map((x, i) => ({
          index: Number(x.index) || i + 1,
          name: String(x.name || runProgress?.current_test_name || 'idle'),
          started_at_ms: Number(x.started_at_ms) || null,
          sse_enabled: Boolean(x.sse_enabled),
          sse_preview: String(x.sse_preview || ''),
          sse_tokens_generated_est: x.sse_tokens_generated_est,
          sse_token_tps_live: x.sse_token_tps_live,
          sse_token_tps_avg: x.sse_token_tps_avg,
          current_step_timings: x.current_step_timings && typeof x.current_step_timings === 'object'
            ? x.current_step_timings
            : null,
        }))
    : [];
  const liveCards = activeLiveCards.length
    ? activeLiveCards
    : [{
        index: 1,
        name: String(runProgress?.current_test_name || 'idle'),
        started_at_ms: currentStepStartedAt || null,
        sse_enabled: Boolean(runProgress?.sse_enabled),
        sse_preview: String(runProgress?.sse_preview || liveSse.text || ''),
        sse_tokens_generated_est: runProgress?.sse_tokens_generated_est,
        sse_token_tps_live: runProgress?.sse_token_tps_live,
        sse_token_tps_avg: runProgress?.sse_token_tps_avg,
        current_step_timings: runProgress?.current_step_timings && typeof runProgress.current_step_timings === 'object'
          ? runProgress.current_step_timings
          : null,
      }];

  const formatSeconds = (v) => {
    const n = Number(v);
    if (!Number.isFinite(n)) return '-';
    return `${n.toFixed(2)} s`;
  };

  const getLiveStepRows = (card) => {
    const cardElapsedMs = card?.started_at_ms
      ? Math.max(0, liveNowMs - Number(card.started_at_ms))
      : currentStepElapsedMs;
    const timings = card?.current_step_timings && typeof card.current_step_timings === 'object'
      ? card.current_step_timings
      : null;
    const liveTotalSeconds = cardElapsedMs != null ? Number(cardElapsedMs) / 1000.0 : timings?.latency_s_total;
    return [
      { key: 'total', value: liveTotalSeconds },
      { key: 'embed', value: timings?.embed_s },
      { key: 'search', value: timings?.search_s },
      { key: 'rerank', value: timings?.rerank_s },
      { key: 'rag', value: timings?.total_rag_s },
      {
        key: 'chat',
        value: timings?.chat_s_estimated != null
          ? timings.chat_s_estimated
          : (cardElapsedMs != null ? Number(cardElapsedMs) / 1000.0 : null),
      },
    ];
  };
  const timingLabel = (key) => ({
    total: 'Total',
    embed: 'Embed',
    search: 'Search',
    rerank: 'Rerank',
    rag: 'RAG',
    chat: 'Chat',
  }[key] || key);
  const renderTimingCards = (rows, keyPrefix = 'timing') => (
    <div className="rag-tests-timing-cards">
      {rows.map((row) => (
        <div key={`${keyPrefix}-${row.key || row.label}`} className="rag-tests-timing-card">
          <span className="rag-tests-timing-card-label">{timingLabel(row.key || row.label)}</span>
          <span className="rag-tests-timing-card-value">
            {row.value != null ? formatSeconds(row.value) : '-'}
          </span>
        </div>
      ))}
    </div>
  );
  const selectedLiveDetailCard = liveCards.find((x) => x.index === liveDetailCardIndex) || liveCards[0] || null;
  const selectedLiveStepRows = selectedLiveDetailCard ? getLiveStepRows(selectedLiveDetailCard) : [];

  useEffect(() => {
    if (!liveCards.length) {
      setLiveDetailCardIndex(null);
      return;
    }
    if (liveDetailCardIndex == null) return;
    if (!liveCards.some((x) => x.index === liveDetailCardIndex)) {
      setLiveDetailCardIndex(liveCards[0].index);
    }
  }, [liveCards, liveDetailCardIndex]);
  const liveTraceChunks = Array.isArray(liveTrace?.rag?.context?.chunks)
    ? liveTrace.rag.context.chunks
    : [];
  const liveTraceQuery = String(liveTrace?.request?.user_query_preview || '').trim();
  const openLiveDetail = () => {
    if (liveDetailCardIndex == null && liveCards[0]?.index != null) {
      setLiveDetailCardIndex(liveCards[0].index);
    }
    setLiveMonitorDetailOpen(true);
  };

  return {
    filteredTests, canRun, hasActiveFilters, hasSelectedTests,
    runAllDisabled, runFilteredDisabled, runSelectedDisabled,
    handleRunAll, handleRunFiltered, handleRunSelected, handleRunSingle, handleCancelRun,
    toggleSelectTest, toggleSelectAll, handleCreateSubmit, handleEditClick, handleEditSubmit,
    handleDeleteClick, failFilters, setFailFilters, tableRows, currentStepElapsedMs,
    liveCards, formatSeconds, getLiveStepRows, timingLabel, renderTimingCards,
    selectedLiveDetailCard, selectedLiveStepRows, liveTraceChunks, liveTraceQuery,
    openLiveDetail, displayResults, failResults, running, runProgress, runError, onStartRun,
  };
}
