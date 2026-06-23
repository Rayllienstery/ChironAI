import React, { useCallback, useEffect, useRef, useState } from "react";
import CreateCollectionIndexProgress, {
  createCollectionFinalLogMetadata,
  formatDurationMs,
} from "../CreateCollectionIndexProgress";
import {
  cancelCreateCollection,
  createCollection,
  getCreateCollectionStatus,
  getProviderCatalog,
  getRagModelSettings,
} from "../../services/api";
import {
  CREATE_COLLECTION_LIVE_ID,
  CREATE_COLLECTION_POLL_INTERVAL_MS,
} from "./constants";

export function useCreateCollectionFlow({
  nc,
  activeSection,
  sources,
  setError,
  loadCollections,
}) {
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState({
    collection_name: "",
    source_ids: [],
    chunk_max_size: 1200,
    chunk_min_size: 300,
    confidence_threshold: 0.75,
    top_k: 4,
    rag_embed_provider_id: "",
    rag_embed_model: "",
    parallel_embed_workers: 4,
  });
  const [createEmbedCatalog, setCreateEmbedCatalog] = useState({ providers: [], models: [] });
  const [createEmbedDefaults, setCreateEmbedDefaults] = useState({
    rag_embed_provider_id: "",
    rag_embed_model: "",
  });
  const [creating, setCreating] = useState(false);
  const [createJobId, setCreateJobId] = useState(null);
  const [createProgress, setCreateProgress] = useState(null);
  const [createCanceling, setCreateCanceling] = useState(false);
  const [showCreateToast, setShowCreateToast] = useState(false);
  const [createCollectionName, setCreateCollectionName] = useState("");
  const createToastTimeoutRef = useRef(null);
  const createPersistedJobRef = useRef(null);
  useEffect(() => {
    if (!showCreateModal) return undefined;
    let cancelled = false;
    (async () => {
      try {
        const [catalog, settings] = await Promise.all([
          getProviderCatalog("embed"),
          getRagModelSettings(),
        ]);
        if (cancelled) return;
        setCreateEmbedCatalog({
          providers: Array.isArray(catalog?.providers) ? catalog.providers : [],
          models: Array.isArray(catalog?.models) ? catalog.models : [],
        });
        const defProvider = (settings?.defaults?.rag_embed_provider_id || "").trim();
        const def = (settings?.defaults?.rag_embed_model || "").trim();
        const savedProvider = (settings?.rag_embed_provider_id || "").trim();
        const saved = (settings?.rag_embed_model || "").trim();
        const catalogModels = Array.isArray(catalog?.models) ? catalog.models : [];
        const savedModelProvider = saved
          ? String(
              catalogModels.find((m) => String(m.id || "").trim() === saved)
                ?.provider_id || "",
            ).trim()
          : "";
        const defModelProvider = def
          ? String(
              catalogModels.find((m) => String(m.id || "").trim() === def)
                ?.provider_id || "",
            ).trim()
          : "";
        setCreateEmbedDefaults({
          rag_embed_provider_id: defProvider,
          rag_embed_model: def,
        });
        setCreateForm((prev) => ({
          ...prev,
          rag_embed_provider_id:
            prev.rag_embed_provider_id ||
            savedProvider ||
            savedModelProvider ||
            defProvider ||
            defModelProvider,
          rag_embed_model: prev.rag_embed_model || saved || def,
        }));
      } catch (e) {
        console.warn("Failed to load embedding models for create collection:", e);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [showCreateModal]);

  // Poll create-collection job progress
  useEffect(() => {
    if (!createJobId) return;
    let disposed = false;
    let timeoutId = null;

    const poll = async () => {
      let shouldContinue = true;
      try {
        const job = await getCreateCollectionStatus(createJobId);
        const nextProgress = {
          status: job.status,
          collection_name: job.collection_name ?? "",
          processed_pages: job.processed_pages ?? 0,
          total_pages: job.total_pages ?? 0,
          indexed_pages: job.indexed_pages ?? 0,
          prepared_pages: job.prepared_pages ?? 0,
          total_chunks: job.total_chunks ?? 0,
          prepared_chunks: job.prepared_chunks ?? 0,
          skipped_pages: job.skipped_pages ?? 0,
          skip_reasons: job.skip_reasons ?? {},
          source_ids: job.source_ids ?? [],
          current_source_id: job.current_source_id ?? "",
          current_filename: job.current_filename ?? "",
          current_phase: job.current_phase ?? "",
          last_skip_reason: job.last_skip_reason ?? "",
          cancel_requested: job.cancel_requested ?? false,
          cancelled: job.cancelled ?? false,
          errors: job.errors ?? [],
          recent_skips: job.recent_skips ?? [],
          skip_log: job.skip_log ?? [],
          skip_log_count: job.skip_log_count ?? 0,
          largest_prepare_removals: job.largest_prepare_removals ?? [],
          deduped_chunks: job.deduped_chunks ?? 0,
          prepare_original_chars: job.prepare_original_chars ?? 0,
          prepare_output_chars: job.prepare_output_chars ?? 0,
          prepare_removed_chars: job.prepare_removed_chars ?? 0,
          empty_after_prepare_removed_chars:
            job.empty_after_prepare_removed_chars ?? 0,
          current_embedding_chars: job.current_embedding_chars ?? 0,
          current_embedding_chunks: job.current_embedding_chunks ?? 0,
          current_embedding_chunk_ms: job.current_embedding_chunk_ms ?? 0,
          embedding_history: job.embedding_history ?? [],
          parallel_embed_workers: job.parallel_embed_workers ?? 0,
          elapsed_ms: job.elapsed_ms ?? 0,
          current_phase_elapsed_ms: job.current_phase_elapsed_ms ?? 0,
          phase_durations_ms: job.phase_durations_ms ?? {},
          error: job.error,
          statistics: job.statistics,
        };
        setCreateProgress(nextProgress);
        if (job.status === "success") {
          shouldContinue = false;
          if (nc?.persistNotification && createPersistedJobRef.current !== createJobId) {
            createPersistedJobRef.current = createJobId;
            const name =
              createCollectionName || job.collection_name || createForm.collection_name || "Collection";
            nc.persistNotification({
              kind: "event",
              source: "crawler",
              title: "Collection created",
              message: `Indexed ${job.indexed_pages ?? 0} pages, ${job.total_chunks ?? 0} chunks${
                job.elapsed_ms ? ` in ${formatDurationMs(job.elapsed_ms)}` : ""
              } (${name})`,
              metadata: createCollectionFinalLogMetadata(nextProgress, createJobId, name),
            });
          }
          setCreateJobId(null);
          setCreating(false);
          setCreateCanceling(false);
          setShowCreateModal(false);
          setCreateForm({
            collection_name: "",
            source_ids: [],
            chunk_max_size: 1200,
            chunk_min_size: 300,
            confidence_threshold: 0.75,
            top_k: 4,
            rag_embed_provider_id: "",
            rag_embed_model: "",
            parallel_embed_workers: 4,
          });
          setShowCreateToast(true);
          await loadCollections();
          alert(
            `Collection created successfully! Indexed ${job.indexed_pages ?? 0} pages, ${job.total_chunks ?? 0} chunks${
              job.elapsed_ms ? ` in ${formatDurationMs(job.elapsed_ms)}` : ""
            }.`,
          );
        } else if (job.status === "failed") {
          shouldContinue = false;
          if (nc?.persistNotification && createPersistedJobRef.current !== createJobId) {
            createPersistedJobRef.current = createJobId;
            const name =
              createCollectionName || job.collection_name || createForm.collection_name || "Collection";
            nc.persistNotification({
              kind: "error",
              source: "crawler",
              title: "Collection failed",
              message: String(job.error || "").slice(0, 400),
              metadata: createCollectionFinalLogMetadata(nextProgress, createJobId, name),
            });
          }
          setCreateJobId(null);
          setCreating(false);
          setCreateCanceling(false);
          setError(job.error || "Collection creation failed");
        } else if (job.status === "cancelled") {
          shouldContinue = false;
          setCreateJobId(null);
          setCreating(false);
          setCreateCanceling(false);
          setShowCreateModal(false);
          setShowCreateToast(true);
        }
      } catch (e) {
        shouldContinue = false;
        setCreateJobId(null);
        setCreating(false);
        setCreateCanceling(false);
        setError(e.message);
      }
      if (!disposed && shouldContinue) {
        timeoutId = window.setTimeout(poll, CREATE_COLLECTION_POLL_INTERVAL_MS);
      }
    };

    poll();

    return () => {
      disposed = true;
      if (timeoutId) window.clearTimeout(timeoutId);
    };
  }, [createJobId]);

  // Auto-hide create-collection toast after completion or failure
  useEffect(() => {
    if (!showCreateToast || !createProgress) {
      return undefined;
    }

    const status = createProgress.status;
    if (status !== "success" && status !== "failed" && status !== "cancelled") {
      return undefined;
    }

    const timeoutMs = status === "success" ? 4000 : 7000;

    if (createToastTimeoutRef.current) {
      clearTimeout(createToastTimeoutRef.current);
    }

    createToastTimeoutRef.current = setTimeout(() => {
      setShowCreateToast(false);
      setCreateProgress(null);
      createToastTimeoutRef.current = null;
    }, timeoutMs);

    return () => {
      if (createToastTimeoutRef.current) {
        clearTimeout(createToastTimeoutRef.current);
        createToastTimeoutRef.current = null;
      }
    };
  }, [createProgress, showCreateToast]);

  useEffect(() => {
    if (!createJobId) {
      createPersistedJobRef.current = null;
    }
  }, [createJobId]);

  useEffect(() => {
    if (!nc?.persistNotification || !createJobId || !createProgress) return;
    const st = createProgress.status;
    if (st !== "success" && st !== "failed") return;
    if (createPersistedJobRef.current === createJobId) return;
    createPersistedJobRef.current = createJobId;
    const name =
      createCollectionName || createForm.collection_name || "Collection";
    nc.persistNotification({
      kind: st === "failed" ? "error" : "event",
      source: "crawler",
      title: st === "success" ? "Collection created" : "Collection failed",
      message:
        st === "failed"
          ? String(createProgress.error || "").slice(0, 400)
          : `Indexed ${createProgress.indexed_pages ?? 0} pages, ${createProgress.total_chunks ?? 0} chunks${
              createProgress.elapsed_ms ? ` in ${formatDurationMs(createProgress.elapsed_ms)}` : ""
            } (${name})`,
      metadata: createCollectionFinalLogMetadata(createProgress, createJobId, name),
    });
  }, [
    nc,
    createJobId,
    createProgress,
    createCollectionName,
    createForm.collection_name,
  ]);
  const handleCreateCollection = async () => {
    if (!createForm.collection_name.trim()) {
      setError("Collection name is required");
      return;
    }
    if (createForm.source_ids.length === 0) {
      setError("At least one source must be selected");
      return;
    }

    setCreating(true);
    setError(null);
    setCreateProgress(null);
    try {
      const trimmedName = createForm.collection_name.trim();
      setCreateCollectionName(trimmedName);
      setShowCreateToast(true);
      nc?.clearLiveSuppression?.(CREATE_COLLECTION_LIVE_ID);
      const result = await createCollection(createForm);
      if (result.job_id) {
        setCreateJobId(result.job_id);
        setCreateCanceling(false);
        setCreateProgress({
          status: "running",
          processed_pages: 0,
          total_pages: 0,
          indexed_pages: 0,
          prepared_pages: 0,
          total_chunks: 0,
          prepared_chunks: 0,
          skipped_pages: 0,
          errors: [],
          recent_skips: [],
          prepare_removed_chars: 0,
          prepare_output_chars: 0,
          empty_after_prepare_removed_chars: 0,
          deduped_chunks: 0,
          current_embedding_chars: 0,
          current_embedding_chunks: 0,
          current_embedding_chunk_ms: 0,
          embedding_history: [],
          parallel_embed_workers: createForm.parallel_embed_workers ?? 4,
          elapsed_ms: 0,
          current_phase_elapsed_ms: 0,
          phase_durations_ms: {},
        });
      } else {
        setShowCreateModal(false);
        setCreateForm({
          collection_name: "",
          source_ids: [],
          chunk_max_size: 1200,
          chunk_min_size: 300,
          confidence_threshold: 0.75,
          top_k: 4,
          rag_embed_provider_id: "",
          rag_embed_model: "",
            parallel_embed_workers: 4,
        });
        await loadCollections();
        alert("Collection created successfully!");
        setCreating(false);
        setShowCreateToast(false);
        setCreateProgress(null);
      }
    } catch (e) {
      setError(e.message);
      setCreating(false);
      setCreateCanceling(false);
      setShowCreateToast(false);
    }
  };

  const handleCancelCreateCollection = async () => {
    if (!createJobId || createCanceling) return;
    setCreateCanceling(true);
    setCreateProgress((prev) => ({
      ...(prev || {}),
      status: "running",
      current_phase: "cancelling",
      cancel_requested: true,
    }));
    try {
      await cancelCreateCollection(createJobId);
    } catch (e) {
      setCreateCanceling(false);
      setError(e.message);
    }
  };

  const handleOpenCreateCollectionDetails = useCallback(() => {
    nc?.clearLiveSuppression?.(CREATE_COLLECTION_LIVE_ID);
    setShowCreateToast(true);
    setShowCreateModal(true);
  }, [nc]);
  const createCollectionToastName =
    createCollectionName || createForm.collection_name || "Collection";
  const createCollectionToastTitle =
    createProgress?.status === "success"
      ? "Collection created"
      : createProgress?.status === "failed"
        ? "Collection failed"
        : createProgress?.status === "cancelled"
          ? "Collection cancelled"
          : "Creating collection...";
  const createCollectionLiveSuppressed =
    nc?.liveSuppressedIds?.includes(CREATE_COLLECTION_LIVE_ID) || false;
  const showCreateCollectionDetailsAction =
    Boolean(createJobId && createProgress) && !showCreateModal;
  useEffect(() => {
    if (
      !nc ||
      activeSection !== "crawler" ||
      !createProgress ||
      !showCreateToast ||
      createCollectionLiveSuppressed
    ) {
      nc?.clearLiveActivity?.(CREATE_COLLECTION_LIVE_ID);
      return undefined;
    }
    nc.setLiveActivity(
      CREATE_COLLECTION_LIVE_ID,
      "crawler",
      <div
        className={`create-collection-live create-collection-live--${createProgress.status || "unknown"}`}
        role="status"
        aria-live="polite"
      >
        <div className="create-collection-live-heading">
          <span className="create-collection-live-title">
            {createCollectionToastTitle}
          </span>
          <span className="create-collection-live-name" title={createCollectionToastName}>
            {createCollectionToastName}
          </span>
        </div>
        {createProgress.status === "failed" && (
          <div className="create-collection-toast-text create-collection-index-error-banner">
            {(createProgress.error && String(createProgress.error).slice(0, 400)) ||
              "Collection creation failed."}
          </div>
        )}
        <CreateCollectionIndexProgress
          progress={createProgress}
          collectionName={createCollectionToastName}
          variant="toast"
          onOpenDetails={
            showCreateCollectionDetailsAction
              ? handleOpenCreateCollectionDetails
              : null
          }
        />
      </div>,
    );
    return () => nc.clearLiveActivity(CREATE_COLLECTION_LIVE_ID);
  }, [
    nc,
    activeSection,
    createProgress,
    showCreateToast,
    createCollectionToastName,
    createCollectionToastTitle,
    createCollectionLiveSuppressed,
    handleOpenCreateCollectionDetails,
    showCreateCollectionDetailsAction,
  ]);
  const toggleSourceInForm = (sourceId) => {
    setCreateForm((prev) => ({
      ...prev,
      source_ids: prev.source_ids.includes(sourceId)
        ? prev.source_ids.filter((id) => id !== sourceId)
        : [...prev.source_ids, sourceId],
    }));
  };

  return {
    showCreateModal,
    setShowCreateModal,
    createForm,
    setCreateForm,
    createEmbedCatalog,
    createEmbedDefaults,
    creating,
    createJobId,
    createProgress,
    createCanceling,
    showCreateToast,
    createCollectionName,
    createCollectionToastName,
    createCollectionToastTitle,
    createCollectionLiveSuppressed,
    showCreateCollectionDetailsAction,
    handleCreateCollection,
    handleCancelCreateCollection,
    handleOpenCreateCollectionDetails,
    toggleSourceInForm,
  };
}
