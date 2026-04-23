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
  getProxyTraceCurrent,
  getRagTests,
  getRagTest,
  getRagTestRuns,
  getRagTestRun,
  getRagTestRunsSummary,
  deleteRagTestRuns,
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

const RAG_TESTS_LAST_USED_KEY = 'coreui.rag_tests.last_used.v1';
const LIVE_MONITOR_CLOCK_MS = 167; // ~6Hz visual refresh; backend polling stays slower.

function ragRetrieved(row) {
  if (!row) return false;
  if (row.retrieval_used != null) return Boolean(row.retrieval_used);
  return Boolean(row.rag_used);
}

function groundingOverlap(row) {
  return row?.grounding_overlap === true;
}

function strictRagOk(row) {
  return row?.strict_rag_ok === true;
}

function yesNo(value) {
  if (value == null) return '-';
  return value ? 'Yes' : 'No';
}

function metricVersionLabel(runOrRow) {
  return String(runOrRow?.metrics_version || 'legacy_unknown');
}

function loadLastUsedRagTestsSettings() {
  if (typeof window === 'undefined') return {};
  try {
    const raw = window.localStorage.getItem(RAG_TESTS_LAST_USED_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' ? parsed : {};
  } catch {
    return {};
  }
}

function sortModelsCloudFirst(list) {
  const items = Array.isArray(list) ? [...list] : [];
  const byName = (a, b) => {
    const an = String(a?.name || a?.id || '').toLowerCase();
    const bn = String(b?.name || b?.id || '').toLowerCase();
    return an.localeCompare(bn);
  };
  const cloud = [];
  const other = [];
  items.forEach((m) => {
    if (modelTagLooksCloud(m?.id || m?.name || '')) cloud.push(m);
    else other.push(m);
  });
  cloud.sort(byName);
  other.sort(byName);
  return [...cloud, ...other];
}

function isTransientFetchLikeError(message) {
  const lower = String(message || '').toLowerCase();
  return (
    lower.includes('failed to fetch') ||
    lower.includes('networkerror') ||
    lower.includes('load failed') ||
    lower.includes('typeerror: failed to fetch')
  );
}

function RagTestsTab({
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
  const [models, setModels] = useState([]);
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
  const [historyFilters, setHistoryFilters] = useState({ model: '', from_date: '', to_date: '', status: '' });
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
      const list = await getModels();
      const sorted = sortModelsCloudFirst(list || []);
      setModels(sorted);
      if (sorted?.length && (!selectedModel || !sorted.some((m) => m.id === selectedModel))) {
        const pick = sorted.find((m) => m.id && !isLogicalRagModelId(m.id)) || sorted[0];
        setSelectedModel(pick.id || '');
      }
    } catch (e) {
      const msg = String(e?.message || '');
      if (!isTransientFetchLikeError(msg)) setError(msg);
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
          model: selectedModel || '',
          collection_name: selectedCollection || '',
          prompt_name: selectedPromptName || '',
          temperature: runTemperature,
          top_k: runTopK,
        })
      );
    } catch {
      // ignore storage errors
    }
  }, [selectedModel, selectedCollection, selectedPromptName, runTemperature, runTopK]);

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
      const msg = String(e?.message || '');
      if (!isTransientFetchLikeError(msg)) setError(msg);
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
    const id = window.setTimeout(() => {
      const nodes = document.querySelectorAll('.rag-tests-live-sse');
      nodes.forEach((node) => {
        try {
          node.scrollTop = node.scrollHeight;
        } catch {
          // ignore
        }
      });
    }, 0);
    return () => window.clearTimeout(id);
  }, [runProgress?.active_live, runProgress?.sse_preview, liveSse.text]);

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

  const filteredTests = tests;

  const runBody = (opts = {}) => ({
    model: selectedModel,
    collection_name: selectedCollection || undefined,
    prompt_name: selectedPromptName || undefined,
    temperature: Number.isFinite(runTemperature) ? runTemperature : 0,
    top_k: Number.isFinite(runTopK) && runTopK > 0 ? runTopK : undefined,
    concurrency: Number(runConcurrency) || 1,
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
        sse_token_tps_live: runProgress?.sse_token_tps_live,
        sse_token_tps_avg: runProgress?.sse_token_tps_avg,
        current_step_timings: runProgress?.current_step_timings && typeof runProgress.current_step_timings === 'object'
          ? runProgress.current_step_timings
          : null,
      }];

  const formatDuration = (ms) => {
    if (ms == null || Number.isNaN(Number(ms))) return '-';
    const n = Math.max(0, Math.round(Number(ms)));
    if (n < 1000) return `${n} ms`;
    return `${(n / 1000).toFixed(1)} s`;
  };
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
    return [
      { key: 'total', value: timings?.latency_s_total ?? (cardElapsedMs != null ? Number(cardElapsedMs) / 1000.0 : null) },
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

  const runHistoryResults = runHistoryModal?.run?.results || [];

  const computeStats = (values) => {
    const nums = (values || [])
      .map((v) => Number(v))
      .filter((n) => Number.isFinite(n) && n >= 0);
    if (!nums.length) return null;
    const sorted = [...nums].sort((a, b) => a - b);
    const pick = (p) => {
      const idx = Math.min(sorted.length - 1, Math.max(0, Math.floor((sorted.length - 1) * p)));
      return sorted[idx];
    };
    const sum = sorted.reduce((acc, n) => acc + n, 0);
    return {
      count: sorted.length,
      avg: sum / sorted.length,
      min: sorted[0],
      max: sorted[sorted.length - 1],
      p50: pick(0.5),
      p95: pick(0.95),
    };
  };

  const latencyStatsMs = computeStats(
    runHistoryResults.map((r) => r.latency_ms ?? r.response_time_ms).filter((v) => v != null)
  );
  const stageAvg = (key) => {
    const vals = runHistoryResults
      .map((r) => (r?.rag_timings && typeof r.rag_timings === 'object' ? r.rag_timings[key] : null))
      .filter((v) => Number.isFinite(Number(v)))
      .map((v) => Number(v));
    if (!vals.length) return null;
    return vals.reduce((acc, n) => acc + n, 0) / vals.length;
  };

  const timingAverages = [
    { label: 'embed', value: stageAvg('embed_s') },
    { label: 'search', value: stageAvg('search_s') },
    { label: 'rerank', value: stageAvg('rerank_s') },
    { label: 'rag', value: stageAvg('total_rag_s') },
    { label: 'chat', value: stageAvg('chat_s_estimated') },
    { label: 'total', value: stageAvg('latency_s_total') },
  ];

  const withLatency = runHistoryResults
    .map((r) => ({
      test_id: r.test_id,
      test_name: r.test_name,
      latency_ms: Number(r.latency_ms ?? r.response_time_ms ?? NaN),
      status: r.status,
    }))
    .filter((x) => Number.isFinite(x.latency_ms))
    .sort((a, b) => a.latency_ms - b.latency_ms);
  const fastestTests = withLatency.slice(0, 5);
  const slowestTests = [...withLatency].reverse().slice(0, 5);

  const chunkMap = new Map();
  runHistoryResults.forEach((r) => {
    const chunks = Array.isArray(r?.chunks_info) ? r.chunks_info : [];
    chunks.forEach((c) => {
      const key = String(c?.url || `${c?.source || 'unknown'}:${c?.title || c?.id || c?.text_preview || ''}` || '').trim();
      if (!key) return;
      const prev = chunkMap.get(key) || { key, count: 0, scoreSum: 0, scoreCount: 0 };
      prev.count += 1;
      const s = Number(c?.score);
      if (Number.isFinite(s)) {
        prev.scoreSum += s;
        prev.scoreCount += 1;
      }
      chunkMap.set(key, prev);
    });
  });
  const topChunks = [...chunkMap.values()]
    .sort((a, b) => b.count - a.count)
    .slice(0, 10)
    .map((c) => ({ ...c, avgScore: c.scoreCount ? c.scoreSum / c.scoreCount : null }));
  const mostPopularChunk = topChunks[0] || null;

  const normalizeReason = (text) => String(text || '').trim().replace(/\s+/g, ' ').toLowerCase();
  const reasonMap = new Map();
  runHistoryResults.forEach((r) => {
    const raw = String(r?.failure_reason || r?.error || '').trim();
    if (!raw) return;
    const norm = normalizeReason(raw);
    const prev = reasonMap.get(norm) || { normalized: norm, sample: raw, count: 0, tests: [] };
    prev.count += 1;
    if (prev.tests.length < 5) prev.tests.push(r.test_name || r.test_id);
    reasonMap.set(norm, prev);
  });
  const allFailureReasons = [...reasonMap.values()].sort((a, b) => b.count - a.count);
  const topFailureReasons = allFailureReasons.slice(0, 10);
  const failureMaxCount = topFailureReasons.reduce((m, x) => Math.max(m, x.count), 1);

  const passCount = runHistoryResults.filter((r) => String(r.status || '').toUpperCase() === 'PASS').length;
  const failCount = runHistoryResults.filter((r) => String(r.status || '').toUpperCase() === 'FAIL').length;
  const ragRetrievedCount = runHistoryResults.filter((r) => ragRetrieved(r)).length;
  const groundingOverlapCount = runHistoryResults.filter((r) => groundingOverlap(r)).length;
  const strictRagOkCount = runHistoryResults.filter((r) => strictRagOk(r)).length;
  const strictRagTotal = runHistoryResults.filter((r) => r?.strict_rag_ok != null).length;
  const totalCount = runHistoryResults.length;

  const summaryBars = [
    { label: 'PASS', value: passCount },
    { label: 'FAIL', value: failCount },
    { label: 'RAG retrieved', value: ragRetrievedCount },
    { label: 'Grounding overlap', value: groundingOverlapCount },
  ];
  const summaryBarMax = summaryBars.reduce((m, x) => Math.max(m, x.value), 1);

  const formatRunDate = (iso) => {
    if (!iso) return '-';
    try {
      const d = new Date(iso);
      return d.toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' });
    } catch {
      return iso;
    }
  };

  const compareLeftRun = runCompareModal?.left?.run || null;
  const compareRightRun = runCompareModal?.right?.run || null;
  const compareLeftResults = Array.isArray(compareLeftRun?.run?.results)
    ? compareLeftRun.run.results
    : Array.isArray(compareLeftRun?.results)
      ? compareLeftRun.results
      : [];
  const compareRightResults = Array.isArray(compareRightRun?.run?.results)
    ? compareRightRun.run.results
    : Array.isArray(compareRightRun?.results)
      ? compareRightRun.results
      : [];

  const compareCountByStatus = (rows, status) =>
    rows.filter((r) => String(r?.status || '').toUpperCase() === String(status || '').toUpperCase()).length;
  const compareRagRetrievedCount = (rows) => rows.filter((r) => ragRetrieved(r)).length;
  const compareGroundingOverlapCount = (rows) => rows.filter((r) => groundingOverlap(r)).length;
  const compareMeanLatency = (rows) => {
    const vals = rows
      .map((r) => Number(r?.latency_ms ?? r?.response_time_ms))
      .filter((v) => Number.isFinite(v) && v >= 0);
    if (!vals.length) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  };
  const comparePassRate = (rows) => {
    if (!rows.length) return null;
    return (compareCountByStatus(rows, 'PASS') / rows.length) * 100;
  };
  const compareTpsAvg = (rows) => {
    const vals = rows
      .map((r) => Number(r?.tokens_per_second_generated))
      .filter((v) => Number.isFinite(v) && v >= 0);
    if (!vals.length) return null;
    return vals.reduce((a, b) => a + b, 0) / vals.length;
  };
  const compareSummaryRows = [
    {
      key: 'total',
      label: 'Total tests',
      left: compareLeftResults.length,
      right: compareRightResults.length,
      higherIsBetter: null,
    },
    {
      key: 'pass',
      label: 'Passed',
      left: compareCountByStatus(compareLeftResults, 'PASS'),
      right: compareCountByStatus(compareRightResults, 'PASS'),
      higherIsBetter: true,
    },
    {
      key: 'fail',
      label: 'Failed',
      left: compareCountByStatus(compareLeftResults, 'FAIL'),
      right: compareCountByStatus(compareRightResults, 'FAIL'),
      higherIsBetter: false,
    },
    {
      key: 'pass_rate',
      label: 'Pass rate %',
      left: comparePassRate(compareLeftResults),
      right: comparePassRate(compareRightResults),
      higherIsBetter: true,
    },
    {
      key: 'rag_retrieved',
      label: 'RAG retrieved',
      left: compareRagRetrievedCount(compareLeftResults),
      right: compareRagRetrievedCount(compareRightResults),
      higherIsBetter: true,
    },
    {
      key: 'grounding_overlap',
      label: 'Grounding overlap',
      left: compareGroundingOverlapCount(compareLeftResults),
      right: compareGroundingOverlapCount(compareRightResults),
      higherIsBetter: true,
    },
    {
      key: 'latency_avg',
      label: 'Avg latency (ms)',
      left: compareMeanLatency(compareLeftResults),
      right: compareMeanLatency(compareRightResults),
      higherIsBetter: false,
    },
    {
      key: 'tps_avg',
      label: 'Avg tok/s',
      left: compareTpsAvg(compareLeftResults),
      right: compareTpsAvg(compareRightResults),
      higherIsBetter: true,
    },
  ];

  const compareFmt = (v, digits = 0) => {
    if (v == null) return '-';
    const n = Number(v);
    if (!Number.isFinite(n)) return String(v);
    return digits > 0 ? n.toFixed(digits) : String(Math.round(n));
  };
  const compareDeltaText = (left, right, higherIsBetter = null, digits = 0) => {
    const l = Number(left);
    const r = Number(right);
    if (!Number.isFinite(l) || !Number.isFinite(r)) return '·';
    const d = r - l;
    if (Math.abs(d) < 1e-9) return '±0';
    const sign = d > 0 ? '+' : '-';
    const abs = Math.abs(d);
    const body = digits > 0 ? abs.toFixed(digits) : String(Math.round(abs));
    if (higherIsBetter === true) return `${sign}${body}`;
    if (higherIsBetter === false) return `${d < 0 ? '+' : '-'}${body}`;
    return `${sign}${body}`;
  };
  const compareDeltaClass = (text) => {
    const s = String(text || '').trim();
    if (!s || s === '·' || s === '±0') return 'neutral';
    if (s.startsWith('+')) return 'positive';
    if (s.startsWith('-')) return 'negative';
    return 'neutral';
  };
  const parseConfidenceLabel = (label) => {
    const m = String(label || '').match(/^\s*(\d+)\s*\/\s*(\d+)\s*$/);
    if (!m) return null;
    const found = Number(m[1]);
    const total = Number(m[2]);
    if (!Number.isFinite(found) || !Number.isFinite(total) || total <= 0) return null;
    return { found, total, ratio: found / total };
  };
  const compareConfidenceDeltaText = (left, right) => {
    const lc = parseConfidenceLabel(left?.confidence_label);
    const rc = parseConfidenceLabel(right?.confidence_label);
    if (!lc || !rc) return '·';
    if (lc.found === rc.found && lc.total === rc.total) return '±0';
    if (lc.total === rc.total) {
      const d = rc.found - lc.found;
      const sign = d > 0 ? '+' : '-';
      return `${sign}${Math.abs(d)}/${rc.total}`;
    }
    return `${lc.found}/${lc.total}→${rc.found}/${rc.total}`;
  };
  const compareTpsDeltaText = (left, right) => {
    const lt = Number(left?.tokens_per_second_generated);
    const rt = Number(right?.tokens_per_second_generated);
    if (!Number.isFinite(lt) || !Number.isFinite(rt)) return '·';
    return compareDeltaText(lt, rt, true, 2);
  };
  const compareSelectedDeltaText = (left, right, statusDelta, latencyDelta) => {
    if (compareFocus === 'status') return statusDelta;
    if (compareFocus === 'latency') return latencyDelta;
    if (compareFocus === 'tps') return compareTpsDeltaText(left, right);
    if (compareFocus === 'confidence') return compareConfidenceDeltaText(left, right);
    return statusDelta;
  };

  const compareHasTestDiff = (left, right) => {
    if (!left || !right) return true;

    if (compareFocus === 'status') {
      const ls = String(left?.status || '').toUpperCase();
      const rs = String(right?.status || '').toUpperCase();
      return ls !== rs;
    }

    if (compareFocus === 'latency') {
      const ll = Number(left?.latency_ms ?? left?.response_time_ms);
      const rl = Number(right?.latency_ms ?? right?.response_time_ms);
      if (Number.isFinite(ll) !== Number.isFinite(rl)) return true;
      if (!Number.isFinite(ll) || !Number.isFinite(rl)) return false;
      return Math.round(ll) !== Math.round(rl);
    }

    if (compareFocus === 'tps') {
      const lt = Number(left?.tokens_per_second_generated);
      const rt = Number(right?.tokens_per_second_generated);
      if (Number.isFinite(lt) !== Number.isFinite(rt)) return true;
      if (!Number.isFinite(lt) || !Number.isFinite(rt)) return false;
      return Math.abs(lt - rt) > 0.01;
    }

    if (compareFocus === 'confidence') {
      const lc = parseConfidenceLabel(left?.confidence_label);
      const rc = parseConfidenceLabel(right?.confidence_label);
      if (!lc && !rc) return false;
      if (!lc || !rc) return true;
      return lc.found !== rc.found || lc.total !== rc.total;
    }

    return false;
  };

  const testMatchKey = (row, idx) => {
    const id = String(row?.test_id || '').trim();
    if (id) return `id:${id}`;
    const name = String(row?.test_name || '').trim().toLowerCase();
    if (name) return `name:${name}`;
    return `row:${idx}`;
  };
  const bucketByTestKey = (rows) => {
    const out = new Map();
    rows.forEach((r, idx) => {
      const key = testMatchKey(r, idx);
      if (!out.has(key)) out.set(key, []);
      out.get(key).push(r);
    });
    return out;
  };
  const leftBuckets = bucketByTestKey(compareLeftResults);
  const rightBuckets = bucketByTestKey(compareRightResults);
  const allBucketKeys = [...new Set([...leftBuckets.keys(), ...rightBuckets.keys()])];
  const comparePairs = [];
  allBucketKeys.forEach((k) => {
    const leftRows = leftBuckets.get(k) || [];
    const rightRows = rightBuckets.get(k) || [];
    const maxLen = Math.max(leftRows.length, rightRows.length);
    for (let i = 0; i < maxLen; i += 1) {
      comparePairs.push({
        pairKey: `${k}#${i}`,
        left: leftRows[i] || null,
        right: rightRows[i] || null,
      });
    }
  });
  const comparePairRank = (pair) => {
    const left = pair?.left || null;
    const right = pair?.right || null;
    const leftStatus = String(left?.status || '-').toUpperCase();
    const rightStatus = String(right?.status || '-').toUpperCase();
    const leftLatency = Number(left?.latency_ms ?? left?.response_time_ms);
    const rightLatency = Number(right?.latency_ms ?? right?.response_time_ms);
    const leftTps = Number(left?.tokens_per_second_generated);
    const rightTps = Number(right?.tokens_per_second_generated);
    const leftConf = parseConfidenceLabel(left?.confidence_label);
    const rightConf = parseConfidenceLabel(right?.confidence_label);

    if (compareFocus === 'status') {
      let rank = 0;
      if (!left || !right) rank += 200;
      if (leftStatus !== rightStatus) rank += 150;
      if (leftStatus === 'FAIL' || rightStatus === 'FAIL') rank += 120;
      if (leftStatus === 'PASS' && rightStatus === 'PASS') rank += 20;
      return rank;
    }
    if (compareFocus === 'latency') {
      if (!Number.isFinite(leftLatency) || !Number.isFinite(rightLatency)) return -1;
      return Math.abs(rightLatency - leftLatency);
    }
    if (compareFocus === 'tps') {
      if (!Number.isFinite(leftTps) || !Number.isFinite(rightTps)) return -1;
      return Math.abs(rightTps - leftTps);
    }
    if (compareFocus === 'confidence') {
      if (!leftConf || !rightConf) return -1;
      const ratioDiff = Math.abs((rightConf.ratio - leftConf.ratio) * 100);
      const foundDiff = Math.abs(rightConf.found - leftConf.found);
      return ratioDiff + foundDiff;
    }
    return 0;
  };
  const compareVisiblePairs = compareOnlyDiff
    ? comparePairs.filter((p) => compareHasTestDiff(p.left, p.right))
    : comparePairs;
  const compareRenderedPairs = [...compareVisiblePairs].sort((a, b) => {
    const ra = comparePairRank(a);
    const rb = comparePairRank(b);
    if (rb !== ra) return rb - ra;
    const la = String(a?.left?.test_name || a?.right?.test_name || a?.pairKey || '');
    const lb = String(b?.left?.test_name || b?.right?.test_name || b?.pairKey || '');
    return la.localeCompare(lb);
  });

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
          <label className="rag-tests-model-label rag-tests-concurrency-label">
            Parallel tests
            <select
              value={runConcurrency}
              onChange={(e) => setRunConcurrency(Number(e.target.value) || 1)}
              disabled={running}
              className="rag-tests-select rag-tests-concurrency-select"
              aria-label="Number of tests to run in parallel"
            >
              {[1, 2, 3, 4, 5, 6].map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
            <span className="rag-tests-concurrency-hint">Cloud tip: usually best up to 3 at once.</span>
          </label>
          <label className="rag-tests-model-label rag-tests-slider-label">
            Temperature: {Number(runTemperature).toFixed(1)}
            <input
              type="range"
              min="0"
              max="2"
              step="0.1"
              value={runTemperature}
              onChange={(e) => setRunTemperature(Number(e.target.value))}
              disabled={running}
              className="rag-tests-range"
              aria-label="RAG tests temperature"
            />
          </label>
          <label className="rag-tests-model-label rag-tests-slider-label">
            Top K: {Number(runTopK).toFixed(1)}
            <input
              type="range"
              min="0.1"
              max="30"
              step="0.1"
              value={runTopK}
              onChange={(e) => setRunTopK(Number(e.target.value))}
              disabled={running}
              className="rag-tests-range"
              aria-label="RAG tests top k"
            />
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
          <p className="rag-tests-progress-current">
            <span className="rag-tests-progress-current-label">Active:</span>{' '}
            <strong>{runProgress.active_count ?? 0}</strong>
            {' / '}
            <strong>{runProgress.max_concurrency ?? runConcurrency}</strong>
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
            </div>
          </div>
        )}
      </div>

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
                const cardElapsedMs = card?.started_at_ms
                  ? Math.max(0, liveNowMs - Number(card.started_at_ms))
                  : currentStepElapsedMs;
                const hasSse = Boolean(card?.sse_enabled || String(card?.sse_preview || '').trim());
                const sseLabel = !hasSse
                  ? 'not available for this request'
                  : String(card?.sse_preview || '').trim()
                    ? 'streaming'
                    : 'enabled (no chunks yet)';
                return (
                  <section key={`live-card-${card.index}`} className="rag-tests-live-card">
                    <p className="rag-tests-live-line">
                      <strong>Current step:</strong> {card.name || 'idle'}
                    </p>
                    <p className="rag-tests-live-line">
                      <strong>Timer:</strong> {formatDuration(cardElapsedMs)}
                    </p>
                    <p className="rag-tests-live-line">
                      <strong>SSE:</strong> {sseLabel}
                    </p>
                    <p className="rag-tests-live-line">
                      <strong>Tokens/s:</strong>{' '}
                      live {card?.sse_token_tps_live != null ? `${Number(card.sse_token_tps_live).toFixed(2)}` : '-'} | avg {card?.sse_token_tps_avg != null ? `${Number(card.sse_token_tps_avg).toFixed(2)}` : '-'}
                    </p>
                    {card?.sse_preview ? (
                      <pre className="rag-tests-live-sse">{card.sse_preview}</pre>
                    ) : null}
                    <p className="rag-tests-live-line">
                      <strong>Current test timings:</strong>
                    </p>
                    <ul className="rag-tests-live-current-steps">
                      {stepRows.map((row) => (
                        <li key={`card-${card.index}-${row.key}`} className="rag-tests-live-current-step">
                          <span className="rag-tests-live-current-step-name">{row.key}</span>
                          <span className="rag-tests-live-current-step-value">{formatSeconds(row.value)}</span>
                        </li>
                      ))}
                    </ul>
                    <div className="rag-tests-live-actions">
                      <button
                        type="button"
                        className="rag-tests-btn small"
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
              <ul className="rag-tests-live-current-steps">
                {selectedLiveStepRows.map((row) => (
                  <li key={`modal-${row.key}`} className="rag-tests-live-current-step">
                    <span className="rag-tests-live-current-step-name">{row.key}</span>
                    <span className="rag-tests-live-current-step-value">{formatSeconds(row.value)}</span>
                  </li>
                ))}
              </ul>
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
                  style={{ cursor: 'pointer' }}
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
                      className="rag-tests-btn small"
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
              {formatRunDate(runHistoryModal.run?.created_at)} | Model: {runHistoryModal.run?.model} | Passed: {runHistoryModal.run?.passed} | Failed: {runHistoryModal.run?.failed}
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
                  <div className="rag-tests-summary-bars">
                    {timingAverages.map((item) => (
                      <div key={item.label} className="rag-tests-summary-bar-row">
                        <span>{item.label}</span>
                        <span>{item.value != null ? `${item.value.toFixed(2)} s` : '-'}</span>
                      </div>
                    ))}
                  </div>
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
                      <td>{row.confidence_label || '-'}</td>
                      <td>
                        <button
                          type="button"
                          className="rag-tests-btn small"
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
                  {formatRunDate(compareLeftRun?.created_at)} | Model: {compareLeftRun?.model || '-'}
                </p>
                <p className="rag-tests-detail-metrics">id: {String(runCompareModal.left?.id || '-')}</p>
                <p className="rag-tests-detail-metrics">metrics: {metricVersionLabel(compareLeftRun)}</p>
              </section>
              <section className="rag-tests-compare-vs">+ / -</section>
              <section className="rag-tests-compare-run-card">
                <h4>Right run</h4>
                <p className="rag-tests-result-modal-meta">
                  {formatRunDate(compareRightRun?.created_at)} | Model: {compareRightRun?.model || '-'}
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
                      const ragStrict = !!r.rag_strict;
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
