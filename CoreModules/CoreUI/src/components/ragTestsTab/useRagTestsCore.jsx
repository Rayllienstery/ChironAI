import { useCallback, useEffect, useState } from 'react';
import {
  createRagTest,
  deleteRagTest,
  deleteRagTestRuns,
  exportRagTestRun,
  getPrompts,
  getProviderCatalog,
  getProxyTraceCurrent,
  getRagCollections,
  getRagTest,
  getRagTestRun,
  getRagTestRuns,
  getRagTestRunsSummary,
  getRagTests,
  updateRagTest,
} from '../../services/api';
import { isLogicalRagModelId } from '../../constants/llmProxyModels';
import { LIVE_MONITOR_CLOCK_MS, RAG_TESTS_LAST_USED_KEY } from './constants';
import {
  confirmCloudRagRun,
  isTransientFetchLikeError,
  loadLastUsedRagTestsSettings,
  sortModelsCloudFirst,
} from './helpers';

export function useRagTestsCore({
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
  const lastUsed = loadLastUsedRagTestsSettings();
  const [providerCatalog, setProviderCatalog] = useState({ providers: [], models: [] });
  const [selectedProviderId, setSelectedProviderId] = useState(String(lastUsed.provider_id || ''));
  const [selectedModel, setSelectedModel] = useState(String(lastUsed.model || ''));
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
  const [historyFilters, setHistoryFilters] = useState({ provider_id: '', model: '', from_date: '', to_date: '', status: '' });
  const [runSummary, setRunSummary] = useState(null);
  const [runHistoryModal, setRunHistoryModal] = useState(null);
  const [runHistoryModalTab, setRunHistoryModalTab] = useState('summary');
  const [historySectionOpen, setHistorySectionOpen] = useState(false);
  const [compareRunIds, setCompareRunIds] = useState([]);
  const [runCompareLoading, setRunCompareLoading] = useState(false);
  const [runHistoryDeleteLoading, setRunHistoryDeleteLoading] = useState(false);
  const [runCompareModal, setRunCompareModal] = useState(null);
  const [compareOnlyDiff, setCompareOnlyDiff] = useState(false);
  const [compareFocus, setCompareFocus] = useState('status');
  const [showFailDrilldown, setShowFailDrilldown] = useState(false);
  const [collections, setCollections] = useState([]);
  const [selectedCollection, setSelectedCollection] = useState(String(lastUsed.collection_name || ''));
  const [prompts, setPrompts] = useState([]);
  const [selectedPromptName, setSelectedPromptName] = useState(String(lastUsed.prompt_name || ''));
  const [runTemperature, setRunTemperature] = useState(
    Number.isFinite(Number(lastUsed.temperature)) ? Number(lastUsed.temperature) : 0
  );
  const [runTopK, setRunTopK] = useState(
    Number.isFinite(Number(lastUsed.top_k)) ? Number(lastUsed.top_k) : 0.1
  );
  const [runStrictMode, setRunStrictMode] = useState(Boolean(lastUsed.strict_mode));
  const [runConcurrency, setRunConcurrency] = useState(1);
  const [liveMonitorOpen, setLiveMonitorOpen] = useState(true);
  const [liveMonitorDetailOpen, setLiveMonitorDetailOpen] = useState(false);
  const [liveDetailCardIndex, setLiveDetailCardIndex] = useState(null);
  const [currentStepStartedAt, setCurrentStepStartedAt] = useState(null);
  const [liveNowMs, setLiveNowMs] = useState(Date.now());
  const [liveTrace, setLiveTrace] = useState(null);
  const [liveSse, setLiveSse] = useState({
    available: false,
    active: false,
    text: '',
    updatedAt: '',
  });
  const models = sortModelsCloudFirst(
    (providerCatalog.models || []).filter(
      (m) => !selectedProviderId || m.provider_id === selectedProviderId,
    ),
  );

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
      setSelectedPromptName((prev) => {
        if (!prev) return '';
        return list.some((p) => p.name === prev) ? prev : '';
      });
    } catch {
      setPrompts([]);
    }
  }, []);

  const loadModels = useCallback(async () => {
    try {
      const catalog = await getProviderCatalog('chat');
      const providers = catalog?.providers || [];
      const allModels = catalog?.models || [];
      setProviderCatalog({ providers, models: allModels });
      const resolvedProviderId =
        selectedProviderId && providers.some((p) => p.provider_id === selectedProviderId)
          ? selectedProviderId
          : (providers[0]?.provider_id || '');
      if (resolvedProviderId !== selectedProviderId) {
        setSelectedProviderId(resolvedProviderId);
      }
      const scoped = sortModelsCloudFirst(
        allModels.filter((m) => !resolvedProviderId || m.provider_id === resolvedProviderId),
      );
      if (scoped?.length && (!selectedModel || !scoped.some((m) => m.id === selectedModel))) {
        const pick = scoped.find((m) => m.id && !isLogicalRagModelId(m.id)) || scoped[0];
        setSelectedModel(pick.id || '');
      }
    } catch (e) {
      const msg = String(e?.message || '');
      if (!isTransientFetchLikeError(msg)) setError(msg);
    }
  }, [selectedModel, selectedProviderId]);

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
      const msg = String(e?.message || '');
      if (!isTransientFetchLikeError(msg)) {
        setError(msg);
        setTests([]);
      }
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

  useEffect(() => {
    try {
      window.localStorage.setItem(
        RAG_TESTS_LAST_USED_KEY,
        JSON.stringify({
          provider_id: selectedProviderId || '',
          model: selectedModel || '',
          collection_name: selectedCollection || '',
          prompt_name: selectedPromptName || '',
          temperature: runTemperature,
          top_k: runTopK,
          strict_mode: runStrictMode,
        })
      );
    } catch {
      // ignore storage errors
    }
  }, [selectedProviderId, selectedModel, selectedCollection, selectedPromptName, runTemperature, runTopK, runStrictMode]);

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
        provider_id: historyFilters.provider_id || undefined,
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
      const msg = String(e?.message || '');
      if (!isTransientFetchLikeError(msg)) setError(msg);
    } finally {
      setRunHistoryLoading(false);
      setRunHistoryLoadingMore(false);
    }
  }, [historyFilters.provider_id, historyFilters.model, historyFilters.from_date, historyFilters.to_date, historyFilters.status]);

  useEffect(() => {
    loadRunHistory(0);
  }, [loadRunHistory]);

  const loadRunSummary = useCallback(async () => {
    try {
      const summary = await getRagTestRunsSummary({
        limit: 50,
        provider_id: historyFilters.provider_id || undefined,
        model: historyFilters.model || undefined,
        from_date: historyFilters.from_date || undefined,
        to_date: historyFilters.to_date || undefined,
      });
      setRunSummary(summary);
    } catch {
      setRunSummary(null);
    }
  }, [historyFilters.provider_id, historyFilters.model, historyFilters.from_date, historyFilters.to_date]);

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
    if (!running) {
      setCurrentStepStartedAt(null);
      setLiveDetailCardIndex(null);
      return;
    }
    if (runProgress?.current_test_name) {
      setCurrentStepStartedAt(Date.now());
    }
  }, [running, runProgress?.current_index, runProgress?.current_test_name]);

  useEffect(() => {
    if (!running || !liveMonitorOpen) return undefined;
    const id = setInterval(() => setLiveNowMs(Date.now()), LIVE_MONITOR_CLOCK_MS);
    return () => clearInterval(id);
  }, [running, liveMonitorOpen]);

  useEffect(() => {
    if (!running || !liveMonitorOpen) {
      setLiveSse((prev) => ({ ...prev, available: false, active: false, text: '' }));
      setLiveTrace(null);
      return undefined;
    }
    const progressAvailable = Boolean(runProgress?.sse_enabled);
    const progressPreview = String(runProgress?.sse_preview || '');
    let cancelled = false;
    let timer = null;

    const tick = async () => {
      try {
        const data = await getProxyTraceCurrent();
        if (cancelled) return;
        const trace = data?.trace || null;
        setLiveTrace(trace);
        const streamEnabled = Boolean(trace?.request?.stream || trace?.ollama?.chat_stream);
        const preview = String(trace?.response?.content_preview || '');
        if (!progressAvailable && !progressPreview) {
          setLiveSse({
            available: streamEnabled,
            active: streamEnabled && preview.trim() !== '',
            text: preview,
            updatedAt: String(data?.updated_at || ''),
          });
        }
      } catch {
        if (!cancelled) {
          setLiveSse((prev) => ({ ...prev, available: false, active: false }));
          setLiveTrace(null);
        }
      } finally {
        if (!cancelled) timer = setTimeout(tick, 900);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [running, liveMonitorOpen, runJobId, runProgress?.sse_enabled, runProgress?.sse_preview]);

  useEffect(() => {
    if (!running) return;
    const progressPreview = String(runProgress?.sse_preview || '');
    const progressAvailable = Boolean(runProgress?.sse_enabled);
    if (!progressAvailable && !progressPreview) return;
    setLiveSse((prev) => {
      const nextText = progressPreview || '';
      return {
        ...prev,
        available: progressAvailable,
        active: progressAvailable && nextText.trim() !== '',
        text: nextText,
      };
    });
  }, [running, runProgress?.sse_enabled, runProgress?.sse_preview]);

  useEffect(() => {
    if (!resultDetailModal && !liveMonitorDetailOpen && !runHistoryModal && !historySectionOpen && !runCompareModal) return undefined;
    const onKey = (e) => {
      if (e.key !== 'Escape') return;
      setResultDetailModal(null);
      setLiveMonitorDetailOpen(false);
      setRunHistoryModal(null);
      setHistorySectionOpen(false);
      setRunCompareModal(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [resultDetailModal, liveMonitorDetailOpen, runHistoryModal, historySectionOpen, runCompareModal]);

  const toggleCompareRun = useCallback((runId) => {
    const key = String(runId || '').trim();
    if (!key) return;
    setCompareRunIds((prev) => {
      if (prev.includes(key)) return prev.filter((x) => x !== key);
      if (prev.length < 2) return [...prev, key];
      return [prev[1], key];
    });
  }, []);

  const clearCompareRuns = useCallback(() => setCompareRunIds([]), []);

  const refreshRunHistoryStateAfterDelete = useCallback(async (deletedIds = null) => {
    await loadRunHistory(0);
    if (historySectionOpen) {
      await loadRunSummary();
    }
    if (Array.isArray(deletedIds) && deletedIds.length > 0) {
      const deleted = new Set(deletedIds.map((id) => String(id)));
      setCompareRunIds((prev) => prev.filter((id) => !deleted.has(String(id))));
      if (runHistoryModal?.run?.id && deleted.has(String(runHistoryModal.run.id))) {
        setRunHistoryModal(null);
      }
    }
  }, [historySectionOpen, loadRunHistory, loadRunSummary, runHistoryModal]);

  const handleDeleteCancelledRuns = useCallback(async () => {
    if (runHistoryDeleteLoading) return;
    const confirmed = window.confirm('Delete all cancelled runs from history?');
    if (!confirmed) return;
    setRunHistoryDeleteLoading(true);
    setError(null);
    try {
      await deleteRagTestRuns({ delete_cancelled: true });
      setCompareRunIds((prev) => prev.filter((id) => {
        const run = runHistory.find((item) => String(item.id) === String(id));
        return run?.status !== 'cancelled';
      }));
      await refreshRunHistoryStateAfterDelete();
    } catch (e) {
      setError(String(e?.message || 'Failed to delete cancelled runs'));
    } finally {
      setRunHistoryDeleteLoading(false);
    }
  }, [refreshRunHistoryStateAfterDelete, runHistoryDeleteLoading, runHistory]);

  const handleDeleteLowPassRuns = useCallback(async () => {
    if (runHistoryDeleteLoading) return;
    const confirmed = window.confirm('Delete all runs with pass rate below 25%?');
    if (!confirmed) return;
    setRunHistoryDeleteLoading(true);
    setError(null);
    try {
      await deleteRagTestRuns({ delete_low_pass: true, max_pass_rate_pct: 25 });
      setCompareRunIds((prev) => prev.filter((id) => {
        const run = runHistory.find((item) => String(item.id) === String(id));
        if (!run) return true;
        const total = Number(run.total || 0);
        const passed = Number(run.passed || 0);
        const passRate = total > 0 ? (passed / total) * 100 : 0;
        return passRate >= 25;
      }));
      await refreshRunHistoryStateAfterDelete();
    } catch (e) {
      setError(String(e?.message || 'Failed to delete low-pass runs'));
    } finally {
      setRunHistoryDeleteLoading(false);
    }
  }, [refreshRunHistoryStateAfterDelete, runHistoryDeleteLoading, runHistory]);

  const handleDeleteSelectedRuns = useCallback(async () => {
    if (runHistoryDeleteLoading || compareRunIds.length === 0) return;
    const confirmed = window.confirm(`Delete ${compareRunIds.length} selected run(s) from history?`);
    if (!confirmed) return;
    const idsToDelete = [...compareRunIds];
    setRunHistoryDeleteLoading(true);
    setError(null);
    try {
      await deleteRagTestRuns({ run_ids: idsToDelete });
      await refreshRunHistoryStateAfterDelete(idsToDelete);
    } catch (e) {
      setError(String(e?.message || 'Failed to delete selected runs'));
    } finally {
      setRunHistoryDeleteLoading(false);
    }
  }, [compareRunIds, refreshRunHistoryStateAfterDelete, runHistoryDeleteLoading]);

  const handleOpenRunCompare = useCallback(async () => {
    if (compareRunIds.length !== 2) return;
    setError(null);
    setRunCompareLoading(true);
    try {
      const [firstId, secondId] = compareRunIds;
      const [firstRun, secondRun] = await Promise.all([
        getRagTestRun(firstId),
        getRagTestRun(secondId),
      ]);
      const ts = (run) => {
        const raw = run?.run?.created_at ?? run?.created_at;
        const n = Date.parse(String(raw || ''));
        return Number.isFinite(n) ? n : -1;
      };
      // Always render newer run on the right side.
      const firstTs = ts(firstRun);
      const secondTs = ts(secondRun);
      const firstIsOlderOrEqual = firstTs <= secondTs;
      const leftId = firstIsOlderOrEqual ? firstId : secondId;
      const rightId = firstIsOlderOrEqual ? secondId : firstId;
      const leftRun = firstIsOlderOrEqual ? firstRun : secondRun;
      const rightRun = firstIsOlderOrEqual ? secondRun : firstRun;
      setRunCompareModal({
        left: { id: leftId, run: leftRun },
        right: { id: rightId, run: rightRun },
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setRunCompareLoading(false);
    }
  }, [compareRunIds]);

  const handleSelectPastRun = useCallback(async (runId) => {
    setError(null);
    try {
      const run = await getRagTestRun(runId);
      setRunHistoryModalTab('summary');
      setRunHistoryModal({ id: runId, run });
      setResultDetailModal(null);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    const rid = String(pendingOpenRunId || '').trim();
    if (!rid) return;
    void handleSelectPastRun(rid);
    if (typeof onPendingOpenHandled === 'function') {
      onPendingOpenHandled();
    }
  }, [pendingOpenRunId, onPendingOpenHandled, handleSelectPastRun]);

  return {
    providerCatalog, selectedProviderId, setSelectedProviderId,
    selectedModel, setSelectedModel, tests, filters, setFilters, filterOptions,
    error, setError, resultDetailModal, setResultDetailModal, selectedTestIds,
    createOpen, setCreateOpen, createForm, setCreateForm, createSubmitting, createConceptsWarning,
    editOpen, setEditOpen, editTestId, setEditTestId, editForm, setEditForm,
    editSubmitting, editConceptsWarning, runHistory, runHistoryLoading, runHistoryLoadingMore,
    runHistoryHasMore, historyFilters, setHistoryFilters, runSummary, runHistoryModal,
    setRunHistoryModal, runHistoryModalTab, setRunHistoryModalTab, historySectionOpen,
    setHistorySectionOpen, compareRunIds, setCompareRunIds, runCompareLoading, setRunCompareLoading,
    runHistoryDeleteLoading, setRunHistoryDeleteLoading, runCompareModal, setRunCompareModal,
    compareOnlyDiff, setCompareOnlyDiff, compareFocus, setCompareFocus, showFailDrilldown,
    setShowFailDrilldown, collections, selectedCollection, setSelectedCollection, prompts,
    selectedPromptName, setSelectedPromptName, runTemperature, setRunTemperature, runTopK,
    setRunTopK, runStrictMode, setRunStrictMode, runConcurrency, liveMonitorOpen,
    setLiveMonitorOpen, liveMonitorDetailOpen, setLiveMonitorDetailOpen, liveDetailCardIndex,
    setLiveDetailCardIndex, currentStepStartedAt, setCurrentStepStartedAt, liveNowMs,
    setLiveNowMs, liveTrace, setLiveTrace, liveSse, setLiveSse, models, loadRunHistory,
    loadTests, toggleCompareRun, clearCompareRuns, handleDeleteCancelledRuns,
    handleDeleteLowPassRuns, handleDeleteSelectedRuns, handleOpenRunCompare, handleSelectPastRun,
  };
}
