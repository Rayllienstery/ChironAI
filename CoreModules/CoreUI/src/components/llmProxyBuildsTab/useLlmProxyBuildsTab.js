import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  getLlmProxyBuilds,
  getModelSettings,
  getPipelinePreview,
  getPrompts,
  getProviderCatalog,
  getRagCollections,
  getRagModelSettings,
  previewLlmProxyBuildModel,
  putLlmProxyBuilds,
} from '../../services/api';
import { getMatchingParameterPrefab, mergeBuildDraftIntoPipelinePreview, buildToDraft, draftToPayload, emptyDraft } from './helpers';

export function useLlmProxyBuildsTab({ focusSubTab, onFocusSubTabConsumed }) {
  const perfMarksRef = useRef({
    mountMark: `llmproxybuilds:mount:${Math.random().toString(16).slice(2)}`,
    firstDataMark: `llmproxybuilds:first_data:${Math.random().toString(16).slice(2)}`,
    didFirstData: false,
  });

  useEffect(() => {
    try {
      performance.mark(perfMarksRef.current.mountMark);
    } catch {
      /* ignore */
    }
  }, []);

  const [sectionTab, setSectionTab] = useState('builds');
  const [builds, setBuilds] = useState([]);
  const [urls, setUrls] = useState({ main: '' });
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [saving, setSaving] = useState(false);
  const [providerCatalog, setProviderCatalog] = useState({ providers: [], models: [] });
  const [prompts, setPrompts] = useState([]);
  const [ragCollections, setRagCollections] = useState([]);
  const [proxyDefaults, setProxyDefaults] = useState(null);
  const [draft, setDraft] = useState(null);
  const [editingId, setEditingId] = useState(null);
  const [detailId, setDetailId] = useState(null);
  const [detailModalBuild, setDetailModalBuild] = useState(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [previewMsg, setPreviewMsg] = useState(null);
  const [buildModalPipelineSnap, setBuildModalPipelineSnap] = useState(null);
  const [buildModalHybrid, setBuildModalHybrid] = useState(true);
  const [buildModalRerank, setBuildModalRerank] = useState(false);
  const [openMenuModel, setOpenMenuModel] = useState(null);
  const modelMenuRootRef = useRef(null);
  const [rowBusy, setRowBusy] = useState({});
  const [wizardStep, setWizardStep] = useState(0);
  const [wizardDirection, setWizardDirection] = useState('forward');

  const chatProviders = useMemo(
    () => (Array.isArray(providerCatalog.providers) ? providerCatalog.providers : []),
    [providerCatalog],
  );

  const load = useCallback(async () => {
    setErr(null);
    setLoading(true);
    try {
      const fast = await getLlmProxyBuilds({ diagnostics: false });
      setBuilds(fast.builds || []);
      setUrls(fast.openai_models_urls || {});
      if (!perfMarksRef.current.didFirstData) {
        perfMarksRef.current.didFirstData = true;
        try {
          performance.mark(perfMarksRef.current.firstDataMark);
          performance.measure(
            'llmproxybuilds:time_to_first_data_ms',
            perfMarksRef.current.mountMark,
            perfMarksRef.current.firstDataMark,
          );
        } catch {
          /* ignore */
        }
      }
    } catch (e) {
      setErr(String(e.message || e));
      setBuilds([]);
      setUrls({});
      setLoading(false);
      return;
    }
    setLoading(false);

    try {
      const full = await getLlmProxyBuilds({ diagnostics: true });
      setBuilds(full.builds || []);
      setUrls(full.openai_models_urls || {});
    } catch {
      /* keep fast snapshot; diagnostics optional */
    }
  }, []);

  const loadEditorDependencies = useCallback(async () => {
    const [catalogResult, promptsResult, settingsResult, collectionsResult] = await Promise.allSettled([
      getProviderCatalog('chat'),
      getPrompts(),
      getModelSettings(),
      getRagCollections().catch(() => ({ collections: [] })),
    ]);

    setProviderCatalog(
      catalogResult.status === 'fulfilled'
        ? {
            providers: Array.isArray(catalogResult.value?.providers) ? catalogResult.value.providers : [],
            models: Array.isArray(catalogResult.value?.models) ? catalogResult.value.models : [],
          }
        : { providers: [], models: [] },
    );
    setPrompts(
      promptsResult.status === 'fulfilled' && Array.isArray(promptsResult.value?.prompts)
        ? promptsResult.value.prompts
        : [],
    );
    setProxyDefaults(settingsResult.status === 'fulfilled' ? settingsResult.value || null : null);
    setRagCollections(
      collectionsResult.status === 'fulfilled' && Array.isArray(collectionsResult.value?.collections)
        ? collectionsResult.value.collections
        : [],
    );
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!draft) return;
    loadEditorDependencies().catch(() => {});
  }, [draft, loadEditorDependencies]);

  useEffect(() => {
    if (!openMenuModel) return undefined;
    const onPointerDown = (e) => {
      if (modelMenuRootRef.current?.contains(e.target)) return;
      setOpenMenuModel(null);
    };
    const onKeyDown = (e) => {
      if (e.key === 'Escape') setOpenMenuModel(null);
    };
    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [openMenuModel]);

  useEffect(() => {
    if (focusSubTab !== 'autocomplete') return;
    setSectionTab('autocomplete');
    if (typeof onFocusSubTabConsumed === 'function') {
      onFocusSubTabConsumed();
    }
  }, [focusSubTab, onFocusSubTabConsumed]);

  useEffect(() => {
    if (!draft || draft.provider_id || chatProviders.length === 0) return;
    setDraft((prev) => (prev ? { ...prev, provider_id: String(chatProviders[0]?.provider_id || '') } : prev));
  }, [chatProviders, draft]);

  const buildModalOpen = Boolean(draft);

  useEffect(() => {
    if (!draft) {
      setBuildModalPipelineSnap(null);
      return undefined;
    }
    let cancelled = false;
    (async () => {
      try {
        const [p, r] = await Promise.all([getPipelinePreview(), getRagModelSettings()]);
        if (cancelled) return;
        setBuildModalPipelineSnap(p);
        setBuildModalHybrid(r?.hybrid_sparse_enabled !== false);
        setBuildModalRerank(Boolean(r?.rerank_for_rag));
      } catch {
        if (!cancelled) setBuildModalPipelineSnap(null);
      }
    })();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- draft read from latest render when deps change
  }, [buildModalOpen]);

  const buildModalPipelineData = useMemo(
    () =>
      mergeBuildDraftIntoPipelinePreview(
        buildModalPipelineSnap,
        buildModalHybrid,
        buildModalRerank,
        draft,
      ),
    [buildModalPipelineSnap, buildModalHybrid, buildModalRerank, draft],
  );

  const filteredModels = useMemo(() => {
    const models = Array.isArray(providerCatalog.models) ? providerCatalog.models : [];
    const providerId = String(draft?.provider_id || '').trim();
    if (!providerId) return models;
    return models.filter((model) => String(model.provider_id || '').trim() === providerId);
  }, [providerCatalog, draft]);

  const isFormValid = useMemo(() => {
    if (!draft) return false;
    return Boolean(draft.id?.trim()) && Boolean(draft.provider_id?.trim()) && Boolean(draft.model?.trim());
  }, [draft]);

  const detailBuild = useMemo(
    () => builds.find((x) => x.id === detailId) || null,
    [builds, detailId],
  );
  const matchingParameterPrefab = getMatchingParameterPrefab(draft);

  const applyParameterPrefab = useCallback((prefab) => {
    setDraft((prev) => {
      if (!prev) return prev;
      return {
        ...prev,
        num_ctx: String(prefab.values.num_ctx),
        num_predict: String(prefab.values.num_predict),
        max_agent_steps: String(prefab.values.max_agent_steps),
      };
    });
  }, []);

  const openNew = () => {
    setDetailId(null);
    setEditingId(null);
    setDraft(emptyDraft());
    setPreviewMsg(null);
    setWizardStep(0);
    setWizardDirection('forward');
  };

  const openEdit = (b) => {
    setDetailId(null);
    setEditingId(b.id);
    setDraft(buildToDraft(b));
    setPreviewMsg(null);
    setWizardStep(0);
    setWizardDirection('forward');
  };

  const openDetails = (bid) => {
    setDraft(null);
    setEditingId(null);
    setPreviewMsg(null);
    setDetailId(bid);
  };

  const closeForm = () => {
    setDraft(null);
    setEditingId(null);
    setPreviewMsg(null);
  };

  const closeDetails = () => {
    setDetailId(null);
  };

  const openDetailModal = (b) => {
    setDetailModalBuild(b);
  };

  const closeDetailModal = () => {
    setDetailModalBuild(null);
  };

  const saveForm = async () => {
    if (!draft) return;
    const payload = draftToPayload(draft);
    let next = builds.map((x) => ({ ...x }));
    if (editingId) {
      const i = next.findIndex((x) => x.id === editingId);
      if (i >= 0) next[i] = { ...next[i], ...payload };
      else next.push(payload);
    } else {
      if (next.some((x) => x.id === payload.id)) {
        setErr(`Build id "${payload.id}" already exists.`);
        return;
      }
      next.push(payload);
    }
    setSaving(true);
    setErr(null);
    try {
      const data = await putLlmProxyBuilds(next);
      setBuilds(data.builds || next);
      closeForm();
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setSaving(false);
    }
  };

  const deleteBuild = async (bid) => {
    if (!window.confirm(`Delete build "${bid}"?`)) return;
    const next = builds.filter((x) => x.id !== bid);
    setSaving(true);
    setErr(null);
    try {
      const data = await putLlmProxyBuilds(next);
      setBuilds(data.builds || next);
      if (detailId === bid) setDetailId(null);
    } catch (e) {
      setErr(String(e.message || e));
    } finally {
      setSaving(false);
    }
  };

  const runPreview = async () => {
    if (!draft?.model?.trim()) {
      setPreviewMsg('Choose a provider model first.');
      return;
    }
    setPreviewBusy(true);
    setPreviewMsg(null);
    try {
      const r = await previewLlmProxyBuildModel(
        String(draft.model).trim(),
        String(draft.provider_id || '').trim(),
      );
      if (r.ok) {
        setPreviewMsg(
          `context_length: ${r.context_length ?? '—'} · thinking: ${r.supports_thinking ? 'yes' : 'no'}`,
        );
      } else setPreviewMsg(r.error || 'Preview failed');
    } catch (e) {
      setPreviewMsg(String(e.message || e));
    } finally {
      setPreviewBusy(false);
    }
  };

  const applySelectedModelDefaults = useCallback(
    async (modelId, providerId) => {
      const mid = String(modelId || '').trim();
      const pid = String(providerId || '').trim();
      if (!mid) return;
      setPreviewBusy(true);
      setPreviewMsg(null);
      try {
        const r = await previewLlmProxyBuildModel(mid, pid);
        const ctxLen = r?.context_length ?? null;
        const thinking = Boolean(r?.supports_thinking);
        setPreviewMsg(`context_length: ${ctxLen ?? '—'} · thinking: ${thinking ? 'yes' : 'no'}`);

        setDraft((prev) => {
          if (!prev || String(prev.model || '').trim() !== mid) return prev;
          const next = { ...prev };
          const t = proxyDefaults?.temperature;
          const tp = proxyDefaults?.top_p;
          if (String(next.temperature || '').trim() === '' && t != null) next.temperature = String(t);
          if (String(next.top_p || '').trim() === '' && tp != null) next.top_p = String(tp);
          if (String(next.num_predict || '').trim() === '') next.num_predict = '65536';
          if (String(next.num_ctx || '').trim() === '' && ctxLen != null) next.num_ctx = String(ctxLen);
          return next;
        });
      } catch (e) {
        setPreviewMsg(String(e.message || e));
      } finally {
        setPreviewBusy(false);
      }
    },
    [proxyDefaults],
  );

  return {
    sectionTab,
    setSectionTab,
    builds,
    urls,
    loading,
    err,
    saving,
    providerCatalog,
    prompts,
    ragCollections,
    proxyDefaults,
    draft,
    setDraft,
    editingId,
    detailId,
    setDetailId,
    detailModalBuild,
    setDetailModalBuild,
    previewBusy,
    previewMsg,
    buildModalPipelineSnap,
    buildModalHybrid,
    buildModalRerank,
    openMenuModel,
    setOpenMenuModel,
    modelMenuRootRef,
    rowBusy,
    wizardStep,
    setWizardStep,
    wizardDirection,
    setWizardDirection,
    chatProviders,
    load,
    loadEditorDependencies,
    buildModalOpen,
    buildModalPipelineData,
    filteredModels,
    isFormValid,
    detailBuild,
    matchingParameterPrefab: getMatchingParameterPrefab(draft),
    applyParameterPrefab,
    openNew,
    openEdit,
    openDetails,
    closeForm,
    closeDetails,
    openDetailModal,
    closeDetailModal,
    saveForm,
    deleteBuild,
    runPreview,
    applySelectedModelDefaults,
  };
}
