import { useCallback, useEffect, useState } from 'react';
import {
  checkRagTrigger,
  deleteRagKeywordCollection,
  getModelSettings,
  getProviderCatalog,
  getRagCollections,
  getRagFrameworkSettings,
  getRagKeywordCollections,
  getRagModelSettings,
  getRagStatus,
  getRagTriggerSettings,
  saveRagKeywordCollections,
  startRag,
  stopRag,
  updateModelSettings,
  updateRagFrameworkSettings,
  updateRagModelSettings,
  updateRagTriggerSettings,
} from '../../services/api';
import { useMergedPipelinePreview } from '../../hooks/useMergedPipelinePreview';
import { CHIRONAI_RAG_TRACE_EVENT } from '../RagTraceTimeline';
import { capitalize, readMirroredRagTraceFromStorage, wordsInMultipleCollections } from './helpers';

export function useRagTab({ scrollToModelsSection, onModelsSectionScrolled }) {
  const [activeTab, setActiveTab] = useState('main');
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState(null);
  const [collections, setCollections] = useState([]);
  const [keywordCollections, setKeywordCollections] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  const [editCollectionId, setEditCollectionId] = useState(null);
  const [editDraft, setEditDraft] = useState(null);
  const [addWordsCollectionId, setAddWordsCollectionId] = useState(null);
  const [addWordsList, setAddWordsList] = useState([]);
  const [addWordsInput, setAddWordsInput] = useState('');
  const [deleteConfirmId, setDeleteConfirmId] = useState(null);
  const [savingKeywords, setSavingKeywords] = useState(false);
  const [triggerSettings, setTriggerSettings] = useState(null);
  const [triggerThresholdDraft, setTriggerThresholdDraft] = useState('');
  const [triggerSaving, setTriggerSaving] = useState(false);
  const [triggerTestMessage, setTriggerTestMessage] = useState('');
  const [triggerTestResult, setTriggerTestResult] = useState(null);
  const [triggerTestLoading, setTriggerTestLoading] = useState(false);
  const [frameworkSettings, setFrameworkSettings] = useState(null);
  const [frameworkTtlDraft, setFrameworkTtlDraft] = useState('');
  const [savingFrameworkSettings, setSavingFrameworkSettings] = useState(false);

  const [embedCatalog, setEmbedCatalog] = useState({ providers: [], models: [] });
  const [rerankCatalog, setRerankCatalog] = useState({ providers: [], models: [] });
  const [ragModelSettings, setRagModelSettings] = useState({
    rag_embed_provider_id: '',
    rag_embed_model: '',
    hybrid_sparse_enabled: true,
    rerank_for_rag: false,
    rag_rerank_provider_id: '',
    rerank_model: '',
    coverage_aware_selection: false,
    concept_expansion_enabled: false,
    coverage_gate_enabled: false,
    coverage_retry_supplemental_search_enabled: false,
    structured_rag_context_enabled: false,
    pipeline_definition: null,
  });
  const [ragModelDefaults, setRagModelDefaults] = useState({
    rag_embed_provider_id: '',
    rag_embed_model: '',
    hybrid_sparse_enabled: true,
    rag_rerank_provider_id: '',
    rerank_model: '',
  });
  const [retrievalYamlDefaults, setRetrievalYamlDefaults] = useState({
    coverage_aware_selection: false,
    concept_expansion_enabled: false,
    coverage_gate_enabled: false,
    coverage_retry_supplemental_search_enabled: false,
    structured_rag_context_enabled: false,
  });
  const [ragModelSaving, setRagModelSaving] = useState(false);
  const [ragModelSaveNotice, setRagModelSaveNotice] = useState(null);

  const [llmProxyRagSelect, setLlmProxyRagSelect] = useState('');
  const [bindingsNotice, setBindingsNotice] = useState(null);
  const [savingLlmRagBinding, setSavingLlmRagBinding] = useState(false);

  const { merged: pipelineMerged, reload: reloadPipelinePreview } = useMergedPipelinePreview({
    liveHybridSparse: ragModelSettings.hybrid_sparse_enabled,
    liveRerankForRag: ragModelSettings.rerank_for_rag,
  });

  const [mirroredPipelineTrace, setMirroredPipelineTrace] = useState(readMirroredRagTraceFromStorage);

  useEffect(() => {
    const onTrace = (e) => {
      const d = e?.detail;
      if (d && Array.isArray(d.trace) && d.trace.length > 0) {
        setMirroredPipelineTrace({ steps: d.trace, latencyMs: d.latencyMs ?? null });
      }
    };
    window.addEventListener(CHIRONAI_RAG_TRACE_EVENT, onTrace);
    return () => window.removeEventListener(CHIRONAI_RAG_TRACE_EVENT, onTrace);
  }, []);

  useEffect(() => {
    const onVis = () => {
      if (document.visibilityState === 'visible') {
        setMirroredPipelineTrace(readMirroredRagTraceFromStorage());
      }
    };
    document.addEventListener('visibilitychange', onVis);
    return () => document.removeEventListener('visibilitychange', onVis);
  }, []);

  useEffect(() => {
    if (!scrollToModelsSection) return undefined;
    const id = window.setTimeout(() => {
      const el = document.getElementById('rag-qdrant-models-section');
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      onModelsSectionScrolled?.();
    }, 50);
    return () => window.clearTimeout(id);
  }, [scrollToModelsSection, onModelsSectionScrolled]);

  const loadProviderCatalogs = useCallback(async () => {
    try {
      const [embedData, rerankData] = await Promise.all([
        getProviderCatalog('embed'),
        getProviderCatalog('rerank'),
      ]);
      setEmbedCatalog({
        providers: Array.isArray(embedData?.providers) ? embedData.providers : [],
        models: Array.isArray(embedData?.models) ? embedData.models : [],
      });
      setRerankCatalog({
        providers: Array.isArray(rerankData?.providers) ? rerankData.providers : [],
        models: Array.isArray(rerankData?.models) ? rerankData.models : [],
      });
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const loadConsumerBindings = useCallback(async () => {
    setBindingsNotice(null);
    try {
      const ms = await getModelSettings();
      setLlmProxyRagSelect((ms.rag_collection || '').trim());
    } catch (e) {
      setBindingsNotice({ type: 'error', text: e.message || 'Failed to load LLM Proxy RAG binding' });
    }
  }, []);

  const loadRagModelSettings = useCallback(async () => {
    try {
      const data = await getRagModelSettings();
      setRagModelDefaults({
        rag_embed_provider_id: (data?.defaults?.rag_embed_provider_id || '').trim(),
        rag_embed_model: (data?.defaults?.rag_embed_model || '').trim(),
        hybrid_sparse_enabled: data?.defaults?.hybrid_sparse_enabled !== false,
        rag_rerank_provider_id: (data?.defaults?.rag_rerank_provider_id || '').trim(),
        rerank_model: (data?.defaults?.rerank_model || '').trim(),
      });
      const ra = data?.retrieval_advanced || {};
      const ryd = data?.retrieval_yaml_defaults || {};
      setRetrievalYamlDefaults({
        coverage_aware_selection: Boolean(ryd.coverage_aware_selection),
        concept_expansion_enabled: Boolean(ryd.concept_expansion_enabled),
        coverage_gate_enabled: Boolean(ryd.coverage_gate_enabled),
        coverage_retry_supplemental_search_enabled: Boolean(ryd.coverage_retry_supplemental_search_enabled),
        structured_rag_context_enabled: Boolean(ryd.structured_rag_context_enabled),
      });
      setRagModelSettings({
        rag_embed_provider_id: data?.rag_embed_provider_id || '',
        rag_embed_model: data?.rag_embed_model || '',
        hybrid_sparse_enabled: data?.hybrid_sparse_enabled !== false,
        rerank_for_rag: Boolean(data?.rerank_for_rag),
        rag_rerank_provider_id: data?.rag_rerank_provider_id || '',
        rerank_model: data?.rerank_model || '',
        coverage_aware_selection: Boolean(ra.coverage_aware_selection),
        concept_expansion_enabled: Boolean(ra.concept_expansion_enabled),
        coverage_gate_enabled: Boolean(ra.coverage_gate_enabled),
        coverage_retry_supplemental_search_enabled: Boolean(ra.coverage_retry_supplemental_search_enabled),
        structured_rag_context_enabled: Boolean(ra.structured_rag_context_enabled),
        pipeline_definition: data?.pipeline_definition || null,
      });
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const loadStatus = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getRagStatus();
      setStatus(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadCollections = async () => {
    try {
      const data = await getRagCollections();
      setCollections(data.collections || []);
    } catch (e) {
      setError(e.message);
    }
  };

  const loadKeywordCollections = useCallback(async () => {
    try {
      const data = await getRagKeywordCollections();
      setKeywordCollections(data.collections || []);
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const loadTriggerSettings = useCallback(async () => {
    try {
      const data = await getRagTriggerSettings();
      setTriggerSettings(data);
      setTriggerThresholdDraft(String(data.rag_trigger_threshold ?? 2));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  const loadFrameworkSettings = useCallback(async () => {
    try {
      const data = await getRagFrameworkSettings();
      setFrameworkSettings(data);
      setFrameworkTtlDraft(String(data.framework_latest_ttl_days ?? 90));
    } catch (e) {
      setError(e.message);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    loadCollections();
    loadKeywordCollections();
    loadTriggerSettings();
    loadFrameworkSettings();
    loadProviderCatalogs();
    loadRagModelSettings();
    loadConsumerBindings();
  }, [
    loadKeywordCollections,
    loadTriggerSettings,
    loadFrameworkSettings,
    loadProviderCatalogs,
    loadRagModelSettings,
    loadConsumerBindings,
  ]);

  const embedProviders = embedCatalog.providers || [];
  const embedModels = embedCatalog.models || [];
  const rerankProviders = rerankCatalog.providers || [];
  const rerankModels = rerankCatalog.models || [];
  const filteredEmbedModels = embedModels.filter(
    (model) =>
      String(model.provider_id || '').trim() ===
      String(ragModelSettings.rag_embed_provider_id || '').trim(),
  );
  const filteredRerankModels = rerankModels.filter(
    (model) =>
      String(model.provider_id || '').trim() ===
      String(ragModelSettings.rag_rerank_provider_id || '').trim(),
  );

  const handleStart = async () => {
    setBusy(true);
    setError(null);
    try {
      await startRag();
      await loadStatus();
      await loadCollections();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async () => {
    setBusy(true);
    setError(null);
    try {
      await stopRag();
      await loadStatus();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  };

  const isRunning = status?.running;
  const overlappingWords = wordsInMultipleCollections(keywordCollections);
  const qdrantCollectionNames = (collections || []).map((c) => c.name).filter(Boolean);

  const saveLlmProxyRagBinding = async () => {
    const v = (llmProxyRagSelect || '').trim();
    if (v && qdrantCollectionNames.length > 0 && !qdrantCollectionNames.includes(v)) {
      setBindingsNotice({ type: 'error', text: 'Pick a collection from the list or clear to use the config default.' });
      return;
    }
    setSavingLlmRagBinding(true);
    setBindingsNotice(null);
    try {
      await updateModelSettings({ rag_collection: v });
      await loadConsumerBindings();
      setBindingsNotice({ type: 'success', text: 'LLM Proxy RAG collection saved.' });
      window.setTimeout(() => setBindingsNotice(null), 5000);
    } catch (e) {
      setBindingsNotice({ type: 'error', text: e.message || 'Save failed' });
    } finally {
      setSavingLlmRagBinding(false);
    }
  };

  const handleSaveTriggerThreshold = async () => {
    const val = parseInt(triggerThresholdDraft, 10);
    if (Number.isNaN(val) || val < 0 || val > 20) return;
    setTriggerSaving(true);
    setError(null);
    try {
      await updateRagTriggerSettings({ rag_trigger_threshold: val });
      setTriggerSettings((prev) => (prev ? { ...prev, rag_trigger_threshold: val } : { rag_trigger_threshold: val }));
    } catch (e) {
      setError(e.message);
    } finally {
      setTriggerSaving(false);
    }
  };

  const handleCheckTrigger = async () => {
    setTriggerTestLoading(true);
    setTriggerTestResult(null);
    setError(null);
    try {
      const result = await checkRagTrigger(triggerTestMessage);
      setTriggerTestResult(result);
    } catch (e) {
      setError(e.message);
    } finally {
      setTriggerTestLoading(false);
    }
  };

  const handleSaveFrameworkSettings = async () => {
    const val = parseInt(frameworkTtlDraft, 10);
    if (Number.isNaN(val) || val < 1 || val > 3650) return;
    setSavingFrameworkSettings(true);
    setError(null);
    try {
      await updateRagFrameworkSettings({ framework_latest_ttl_days: val });
      setFrameworkSettings((prev) =>
        prev ? { ...prev, framework_latest_ttl_days: val } : { framework_latest_ttl_days: val },
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setSavingFrameworkSettings(false);
    }
  };

  const handleSaveRagModelSettings = async () => {
    setRagModelSaving(true);
    setRagModelSaveNotice(null);
    setError(null);
    try {
      await updateRagModelSettings({
        rag_embed_provider_id: ragModelSettings.rag_embed_provider_id || '',
        rag_embed_model: ragModelSettings.rag_embed_model || '',
        hybrid_sparse_enabled: Boolean(ragModelSettings.hybrid_sparse_enabled),
        rerank_for_rag: Boolean(ragModelSettings.rerank_for_rag),
        rag_rerank_provider_id: ragModelSettings.rag_rerank_provider_id || '',
        rerank_model: ragModelSettings.rerank_model || '',
        coverage_aware_selection: Boolean(ragModelSettings.coverage_aware_selection),
        concept_expansion_enabled: Boolean(ragModelSettings.concept_expansion_enabled),
        coverage_gate_enabled: Boolean(ragModelSettings.coverage_gate_enabled),
        coverage_retry_supplemental_search_enabled: Boolean(
          ragModelSettings.coverage_retry_supplemental_search_enabled,
        ),
        structured_rag_context_enabled: Boolean(ragModelSettings.structured_rag_context_enabled),
      });
      await loadRagModelSettings();
      await reloadPipelinePreview();
      setRagModelSaveNotice({ type: 'success', text: 'Models saved. Values below match the server.' });
      window.setTimeout(() => setRagModelSaveNotice(null), 6000);
    } catch (e) {
      setRagModelSaveNotice({ type: 'error', text: e.message || 'Save failed' });
      setError(e.message);
    } finally {
      setRagModelSaving(false);
    }
  };

  const handleOpenDashboard = () => {
    const url = status?.url || 'http://localhost:6333';
    window.open(`${url}/dashboard#/collections`, '_blank', 'noopener,noreferrer');
  };

  const handleSaveKeywordCollections = async (nextCollections) => {
    setSavingKeywords(true);
    try {
      await saveRagKeywordCollections({ collections: nextCollections });
      await loadKeywordCollections();
      setEditCollectionId(null);
      setEditDraft(null);
      setAddWordsCollectionId(null);
      setAddWordsList([]);
      setAddWordsInput('');
      setDeleteConfirmId(null);
    } catch (e) {
      setError(e.message);
    } finally {
      setSavingKeywords(false);
    }
  };

  const handleToggleEnabled = (coll) => {
    const next = keywordCollections.map((c) =>
      c.id === coll.id ? { ...c, enabled: !c.enabled } : c
    );
    handleSaveKeywordCollections(next);
  };

  const handleStartEdit = (coll) => {
    setEditCollectionId(coll.id);
    setEditDraft({ name: coll.name, keywords: [...(coll.keywords || [])] });
  };

  const handleCancelEdit = () => {
    setEditCollectionId(null);
    setEditDraft(null);
  };

  const handleSaveEdit = () => {
    if (!editDraft || !editCollectionId) return;
    const next = keywordCollections.map((c) =>
      c.id === editCollectionId
        ? { ...c, name: editDraft.name.trim() || c.name, keywords: editDraft.keywords.filter(Boolean) }
        : c
    );
    handleSaveKeywordCollections(next);
  };

  const handleDeleteCollection = async (id) => {
    try {
      await deleteRagKeywordCollection(id);
      await loadKeywordCollections();
      setDeleteConfirmId(null);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleAddCollection = async () => {
    const newColl = {
      id: `new-${Date.now()}`,
      name: 'New collection',
      enabled: true,
      keywords: [],
    };
    const next = [...keywordCollections, newColl];
    await handleSaveKeywordCollections(next);
  };

  const handlePasteIntoCollection = async (coll) => {
    try {
      const text = await navigator.clipboard.readText();
      const words = text.split(/[\s,;\n]+/).map((w) => capitalize(w.trim())).filter(Boolean);
      const seen = new Set((coll.keywords || []).map((k) => k.toLowerCase()));
      const toAdd = words.filter((w) => !seen.has(w.toLowerCase()));
      if (toAdd.length === 0) return;
      const nextKeywords = [...(coll.keywords || []), ...toAdd];
      const next = keywordCollections.map((c) =>
        c.id === coll.id ? { ...c, keywords: nextKeywords } : c
      );
      await handleSaveKeywordCollections(next);
    } catch (e) {
      setError(e.message || 'Clipboard access failed');
    }
  };

  const handleOpenAddWords = (coll) => {
    setAddWordsCollectionId(coll.id);
    setAddWordsList([]);
    setAddWordsInput('');
  };

  const handleAddWordInputKeyDown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const v = (e.target.value || '').trim();
      if (v) {
        setAddWordsList((prev) => [...prev, capitalize(v)]);
        setAddWordsInput('');
      }
    }
  };

  const handleAddWordsSave = () => {
    const coll = keywordCollections.find((c) => c.id === addWordsCollectionId);
    if (!coll) return;
    const seen = new Set((coll.keywords || []).map((k) => k.toLowerCase()));
    const toAdd = addWordsList.filter((w) => !seen.has(w.toLowerCase()));
    if (toAdd.length === 0) {
      setAddWordsCollectionId(null);
      setAddWordsList([]);
      return;
    }
    const nextKeywords = [...(coll.keywords || []), ...toAdd];
    const next = keywordCollections.map((c) =>
      c.id === addWordsCollectionId ? { ...c, keywords: nextKeywords } : c
    );
    handleSaveKeywordCollections(next);
  };

  const handleRefresh = () => {
    loadStatus();
    loadCollections();
    loadKeywordCollections();
    loadTriggerSettings();
    loadFrameworkSettings();
    loadConsumerBindings();
    reloadPipelinePreview();
  };

  return {
    activeTab,
    setActiveTab,
    loading,
    status,
    collections,
    keywordCollections,
    error,
    busy,
    sheetOpen,
    setSheetOpen,
    editCollectionId,
    editDraft,
    setEditDraft,
    addWordsCollectionId,
    setAddWordsCollectionId,
    addWordsList,
    addWordsInput,
    setAddWordsInput,
    deleteConfirmId,
    setDeleteConfirmId,
    savingKeywords,
    triggerSettings,
    triggerThresholdDraft,
    setTriggerThresholdDraft,
    triggerSaving,
    triggerTestMessage,
    setTriggerTestMessage,
    triggerTestResult,
    triggerTestLoading,
    frameworkSettings,
    frameworkTtlDraft,
    setFrameworkTtlDraft,
    savingFrameworkSettings,
    embedCatalog,
    rerankCatalog,
    ragModelSettings,
    setRagModelSettings,
    ragModelDefaults,
    retrievalYamlDefaults,
    ragModelSaving,
    ragModelSaveNotice,
    llmProxyRagSelect,
    setLlmProxyRagSelect,
    bindingsNotice,
    savingLlmRagBinding,
    pipelineMerged,
    mirroredPipelineTrace,
    embedProviders,
    embedModels,
    rerankProviders,
    rerankModels,
    filteredEmbedModels,
    filteredRerankModels,
    handleStart,
    handleStop,
    isRunning,
    overlappingWords,
    qdrantCollectionNames,
    saveLlmProxyRagBinding,
    handleSaveTriggerThreshold,
    handleCheckTrigger,
    handleSaveFrameworkSettings,
    handleSaveRagModelSettings,
    handleOpenDashboard,
    handleToggleEnabled,
    handleStartEdit,
    handleCancelEdit,
    handleSaveEdit,
    handleDeleteCollection,
    handleAddCollection,
    handlePasteIntoCollection,
    handleOpenAddWords,
    handleAddWordInputKeyDown,
    handleAddWordsSave,
    handleRefresh,
  };
}
