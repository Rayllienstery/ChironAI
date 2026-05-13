function ModalShell({ title, onClose, className = "", children, footer, closeDisabled = false }) {
  return (
    <div
      className="modal-overlay"
      onClick={closeDisabled ? undefined : onClose}
    >
      <div
        className={className ? `modal-content ${className}` : "modal-content"}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <h3>{title}</h3>
          <button
            type="button"
            className="modal-close"
            onClick={onClose}
            aria-label="Close"
            disabled={closeDisabled}
          >
            &times;
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-footer">{footer}</div> : null}
      </div>
    </div>
  );
}

const INDEXING_PHASE_LABELS = {
  reading: "Reading file",
  chunking: "Chunking markdown",
  embedding: "Embedding vectors",
  saving: "Writing to Qdrant",
  cancelling: "Cancelling",
  cancelled: "Cancelled",
  idle: "",
  complete: "Complete",
};

const SKIP_REASON_LABELS = {
  read_error: "Read error",
  too_short: "Too short / empty file",
  empty_after_prepare: "Empty after prepare (incl. reject_low_signal pipeline step)",
  chunk_failed: "Chunking failed",
  no_valid_chunks: "No quality chunks",
  embed_failed: "Embedding failed",
  dim_mismatch: "Vector dimension mismatch",
  other: "Other",
};

function CreateCollectionIndexProgress({
  progress,
  collectionName,
  variant,
}) {
  if (!progress) return null;
  const isRunning = progress.status === "running";
  const isSuccess = progress.status === "success";
  const isCancelled = progress.status === "cancelled";
  const sr = progress.skip_reasons || {};
  const skipEntries = Object.entries(sr).filter(([, n]) => n > 0);
  const phaseKey = progress.current_phase || "";
  const phaseLabel = INDEXING_PHASE_LABELS[phaseKey] || phaseKey;
  const total = progress.total_pages || 0;
  const processed = progress.processed_pages ?? 0;
  const pct =
    total > 0 ? Math.min(100, Math.round((100 * processed) / total)) : 0;
  const sourcesLabel = (progress.source_ids || []).join(", ") || "-";
  const currentFile =
    progress.current_filename &&
    `${progress.current_source_id || ""}/${progress.current_filename}`.replace(
      /^\//,
      "",
    );

  return (
    <div
      className={`create-collection-index-progress create-collection-index-progress--${variant}`}
    >
      {isRunning && (
        <div className="create-collection-index-progress__hero">
          <span
            className="create-collection-activity-ring"
            aria-hidden="true"
            title="Indexing in progress"
          >
            <svg
              className="create-collection-activity-ring__svg"
              viewBox="0 0 48 48"
            >
              <circle
                className="create-collection-activity-ring__circle"
                cx="24"
                cy="24"
                r="18"
              />
            </svg>
          </span>
          <div className="create-collection-index-progress__hero-text">
            {variant === "modal" && (
              <div className="create-collection-index-progress__collection">
                {collectionName || "Collection"}
              </div>
            )}
            <div className="create-collection-index-progress__sources">
              Sources: {sourcesLabel}
            </div>
          </div>
        </div>
      )}

      <div className="create-collection-index-stats">
        <div className="create-collection-index-stat">
          <span className="create-collection-index-stat__value create-collection-index-stat__value--ok">
            {progress.indexed_pages ?? 0}
          </span>
          <span className="create-collection-index-stat__label">indexed</span>
        </div>
        <div className="create-collection-index-stat">
          <span className="create-collection-index-stat__value create-collection-index-stat__value--skip">
            {progress.skipped_pages ?? 0}
          </span>
          <span className="create-collection-index-stat__label">skipped</span>
        </div>
        <div className="create-collection-index-stat">
          <span className="create-collection-index-stat__value">
            {progress.total_chunks ?? 0}
          </span>
          <span className="create-collection-index-stat__label">chunks</span>
        </div>
        <div className="create-collection-index-stat">
          <span className="create-collection-index-stat__value">
            {processed} / {total || "..."}
          </span>
          <span className="create-collection-index-stat__label">pages done</span>
        </div>
      </div>

      {isRunning && (currentFile || phaseLabel) && (
        <div className="create-collection-index-current">
          {phaseLabel && phaseKey && (
            <div className="create-collection-index-current__phase">
              <span className="create-collection-index-current__phase-dot" />
              {phaseLabel}
            </div>
          )}
          {currentFile && (
            <div
              className="create-collection-index-current__file"
              title={currentFile}
            >
              {currentFile}
            </div>
          )}
        </div>
      )}

      {skipEntries.length > 0 && (
        <div className="create-collection-index-skips">
          <div className="create-collection-index-skips__title">Skip reasons</div>
          <div className="create-collection-index-skips__pills">
            {skipEntries.map(([key, n]) => (
              <span key={key} className="create-collection-index-skip-pill">
                {SKIP_REASON_LABELS[key] || key}: <strong>{n}</strong>
              </span>
            ))}
          </div>
        </div>
      )}

      {total > 0 && isRunning && (
        <div className="create-collection-toast-progress-bar-wrap create-collection-index-progress__bar">
          <div
            className="create-collection-toast-progress-bar-fill"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}

      {isSuccess && (
        <div className="create-collection-index-done">
          Done: {progress.indexed_pages ?? 0} pages indexed into Qdrant,{" "}
          {progress.skipped_pages ?? 0} skipped, {progress.total_chunks ?? 0}{" "}
          chunks total.
        </div>
      )}

      {isCancelled && (
        <div className="create-collection-index-done">
          Cancelled after {processed} / {total || "..."} pages.
        </div>
      )}

      {progress.errors && progress.errors.length > 0 && (
        <details className="create-collection-index-errors">
          <summary>Recent errors ({progress.errors.length})</summary>
          <ul>
            {progress.errors.map((err, i) => (
              <li key={i}>{String(err)}</li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

function SeedUrlsEditor({ seedUrls, onChange }) {
  const updateSeedUrlAt = (index, value) => {
    const next = [...seedUrls];
    next[index] = value;
    onChange(next);
  };

  return (
    <div className="seed-urls-editor">
      <div className="seed-urls-list-editor">
        {seedUrls.map((url, index) => (
          <div key={index} className="seed-url-item">
            <input
              type="url"
              value={url}
              onChange={(e) => updateSeedUrlAt(index, e.target.value)}
              placeholder="https://example.com/page"
              className="seed-url-input"
            />
            <button
              type="button"
              className="crawler-button small remove"
              onClick={() => onChange(seedUrls.filter((_, i) => i !== index))}
            >
              &times;
            </button>
          </div>
        ))}
      </div>
      <button
        type="button"
        className="crawler-button small"
        onClick={() => onChange([...seedUrls, ""])}
      >
        + Add Seed URL
      </button>
      <div className="form-hint">
        Additional entry points for the crawler. Each URL should be on a new
        line or separate entry.
      </div>
    </div>
  );
}

export function CreatePipelineModal({
  open,
  newPipelineName,
  onChangeName,
  onConfirm,
  onClose,
}) {
  if (!open) return null;
  return (
    <ModalShell title="Create a new pipeline" onClose={onClose}>
      <label className="indexer-select-label">
        Pipeline name (letters, numbers, underscores, hyphens):
        <input
          type="text"
          value={newPipelineName}
          onChange={(e) => onChangeName(e.target.value)}
          className="md-pipeline-param-input"
          placeholder="e.g. apple_docs"
          onKeyDown={(e) => e.key === "Enter" && onConfirm()}
        />
      </label>
      <div className="md-pipeline-modal-actions">
        <button type="button" className="crawler-button primary" onClick={onConfirm}>
          Create
        </button>
        <button type="button" className="crawler-button ghost" onClick={onClose}>
          Cancel
        </button>
      </div>
    </ModalShell>
  );
}

export function DeletePipelineConfirmModal({
  open,
  pipelineName,
  onConfirm,
  onClose,
}) {
  if (!open) return null;
  return (
    <ModalShell
      title="Delete pipeline"
      onClose={onClose}
      className="md-pipeline-delete-confirm"
    >
      <p className="md-pipeline-delete-message">
        Are you sure you want to delete the pipeline &quot;{pipelineName}
        &quot;? This cannot be undone.
      </p>
      <div className="md-pipeline-modal-actions">
        <button type="button" className="crawler-button" onClick={onClose}>
          Cancel
        </button>
        <button
          type="button"
          className="crawler-button primary danger"
          onClick={onConfirm}
        >
          Delete
        </button>
      </div>
    </ModalShell>
  );
}

export function CreateCollectionModal({
  open,
  createProgress,
  createForm,
  onFormChange,
  createEmbedCatalog,
  createEmbedDefaults,
  sources,
  toggleSourceInForm,
  creating,
  createCanceling = false,
  onCreate,
  onCancelCreate,
  onClose,
}) {
  if (!open) return null;
  const isRunning = Boolean(creating || createProgress?.status === "running");
  const embedProviders = Array.isArray(createEmbedCatalog?.providers)
    ? createEmbedCatalog.providers
    : [];
  const embedModels = Array.isArray(createEmbedCatalog?.models)
    ? createEmbedCatalog.models
    : [];
  const currentEmbedProviderId = String(createForm.rag_embed_provider_id || "").trim();
  const defaultEmbedProviderId = String(createEmbedDefaults.rag_embed_provider_id || "").trim();
  const providerById = new Map();
  embedProviders.forEach((provider) => {
    const id = String(provider.provider_id || "").trim();
    if (id) providerById.set(id, provider);
  });
  embedModels.forEach((model) => {
    const id = String(model.provider_id || "").trim();
    if (id && !providerById.has(id)) {
      providerById.set(id, { provider_id: id, title: id });
    }
  });
  [currentEmbedProviderId, defaultEmbedProviderId].forEach((id) => {
    if (id && !providerById.has(id)) {
      providerById.set(id, { provider_id: id, title: id });
    }
  });
  const embedProviderOptions = Array.from(providerById.values());
  const filteredEmbedModels = embedModels.filter(
    (model) =>
      currentEmbedProviderId &&
      String(model.provider_id || "").trim() === currentEmbedProviderId,
  );
  return (
    <ModalShell
      title="Create New Collection"
      onClose={onClose}
      closeDisabled={isRunning}
      footer={
        isRunning ? (
          <button
            type="button"
            className="crawler-button"
            onClick={onCancelCreate}
            disabled={createCanceling}
          >
            {createCanceling ? "Cancelling..." : "Cancel indexing"}
          </button>
        ) : (
          <>
            <button
              type="button"
              className="crawler-button"
              onClick={onClose}
            >
              Cancel
            </button>
            <button
              type="button"
              className="crawler-button primary"
              onClick={onCreate}
            >
              Create Collection
            </button>
          </>
        )
      }
    >
      {createProgress && (
        <div className="create-collection-progress create-collection-progress--detailed">
          {createProgress.status === "failed" && (
            <div className="create-collection-index-error-banner">
              {(createProgress.error && String(createProgress.error).slice(0, 400)) ||
                "Collection creation failed."}
            </div>
          )}
          <CreateCollectionIndexProgress
            progress={createProgress}
            collectionName={createForm.collection_name || "Collection"}
            variant="modal"
          />
        </div>
      )}
      {isRunning ? null : (
        <>
      <div className="form-group">
        <label>Collection Name *</label>
        <input
          type="text"
          value={createForm.collection_name}
          onChange={(e) =>
            onFormChange((prev) => ({
              ...prev,
              collection_name: e.target.value,
            }))
          }
          placeholder="my_collection"
        />
      </div>
      <div className="form-group">
        <label htmlFor="create-collection-embed-provider">Embedding provider</label>
        <select
          id="create-collection-embed-provider"
          value={createForm.rag_embed_provider_id}
          className="coreui-select"
          onChange={(e) =>
            onFormChange((prev) => ({
              ...prev,
              rag_embed_provider_id: e.target.value,
              rag_embed_model: "",
            }))
          }
          disabled={!embedProviderOptions.length && !defaultEmbedProviderId}
        >
          <option value="">
            Select provider
          </option>
          {embedProviderOptions.map((provider) => (
            <option key={provider.provider_id} value={provider.provider_id}>
              {provider.title || provider.provider_id}
            </option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label htmlFor="create-collection-embed-model">Embedding model</label>
        <select
          id="create-collection-embed-model"
          value={createForm.rag_embed_model}
          className="coreui-select"
          onChange={(e) =>
            onFormChange((prev) => ({
              ...prev,
              rag_embed_model: e.target.value,
            }))
          }
          disabled={!currentEmbedProviderId || !filteredEmbedModels.length}
        >
          <option value="">
            {currentEmbedProviderId
              ? "Select model"
              : "Select provider first"}
          </option>
          {createForm.rag_embed_model &&
            !filteredEmbedModels.some((m) => m.id === createForm.rag_embed_model) && (
              <option value={createForm.rag_embed_model}>
                {createForm.rag_embed_model} (saved - not in current provider list)
              </option>
            )}
          {filteredEmbedModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name || m.id}
            </option>
          ))}
        </select>
        <p className="create-collection-embed-hint">
          Same pool as in RAG / Qdrant. Choose a model for this indexing run, or
          leave Server default to use the saved RAG embedding model.
        </p>
      </div>
      <div className="form-group">
        <label htmlFor="create-collection-parallel-workers">
          Parallel embedding requests
        </label>
        <input
          id="create-collection-parallel-workers"
          type="number"
          value={createForm.parallel_embed_workers ?? 2}
          onChange={(e) =>
            onFormChange((prev) => {
              const parsed = parseInt(e.target.value, 10);
              const workers = Number.isFinite(parsed)
                ? Math.min(4, Math.max(1, parsed))
                : 2;
              return {
                ...prev,
                parallel_embed_workers: workers,
              };
            })
          }
          min="1"
          max="4"
          step="1"
          disabled={creating}
        />
        <p className="create-collection-embed-hint">
          Higher values can speed up indexing, but may increase Ollama timeouts
          on limited GPU/VRAM.
        </p>
      </div>
      <div className="form-group">
        <label>Select Sources *</label>
        <div className="sources-checkboxes">
          {sources.map((source) => (
            <label key={source.id} className="checkbox-label">
              <input
                type="checkbox"
                checked={createForm.source_ids.includes(source.id)}
                onChange={() => toggleSourceInForm(source.id)}
              />
              <span>
                {source.id} ({source.total_pages || 0} pages)
              </span>
            </label>
          ))}
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Chunk Max Size</label>
          <input
            type="number"
            value={createForm.chunk_max_size}
            onChange={(e) =>
              onFormChange((prev) => ({
                ...prev,
                chunk_max_size: parseInt(e.target.value, 10) || 1200,
              }))
            }
            min="100"
            max="5000"
          />
        </div>
        <div className="form-group">
          <label>Chunk Min Size</label>
          <input
            type="number"
            value={createForm.chunk_min_size}
            onChange={(e) =>
              onFormChange((prev) => ({
                ...prev,
                chunk_min_size: parseInt(e.target.value, 10) || 300,
              }))
            }
            min="50"
            max="2000"
          />
        </div>
      </div>
      <div className="form-row">
        <div className="form-group">
          <label>Confidence Threshold</label>
          <input
            type="number"
            step="0.01"
            value={createForm.confidence_threshold}
            onChange={(e) =>
              onFormChange((prev) => ({
                ...prev,
                confidence_threshold: parseFloat(e.target.value) || 0.75,
              }))
            }
            min="0"
            max="1"
          />
        </div>
        <div className="form-group">
          <label>Top K</label>
          <input
            type="number"
            value={createForm.top_k}
            onChange={(e) =>
              onFormChange((prev) => ({
                ...prev,
                top_k: parseInt(e.target.value, 10) || 4,
              }))
            }
            min="1"
            max="20"
          />
        </div>
      </div>
        </>
      )}
    </ModalShell>
  );
}

export function SourceModal({
  open,
  mode,
  sourceId,
  form,
  onFormChange,
  loading,
  onSubmit,
  onClose,
}) {
  if (!open) return null;
  const isEdit = mode === "edit";

  return (
    <ModalShell
      title={isEdit ? `Edit Source: ${sourceId}` : "Add New Source"}
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className="crawler-button"
            onClick={onClose}
            disabled={loading}
          >
            Cancel
          </button>
          <button
            type="button"
            className="crawler-button primary"
            onClick={onSubmit}
            disabled={loading}
          >
            {loading
              ? isEdit
                ? "Updating..."
                : "Adding..."
              : isEdit
                ? "Update Source"
                : "Add Source"}
          </button>
        </>
      }
    >
      {isEdit ? (
        <div className="form-group">
          <label>Source ID</label>
          <input
            type="text"
            value={form.id}
            disabled
            className="crawler-input-disabled"
          />
          <div className="form-hint">Source ID cannot be changed</div>
        </div>
      ) : (
        <div className="form-group">
          <label>Source ID *</label>
          <input
            type="text"
            value={form.id}
            onChange={(e) =>
              onFormChange((prev) => ({
                ...prev,
                id: e.target.value,
              }))
            }
            placeholder="my_source"
          />
          <div className="form-hint">
            Alphanumeric, underscores, and hyphens only
          </div>
        </div>
      )}

      <div className="form-group">
        <label>URL *</label>
        <input
          type="url"
          value={form.url}
          onChange={(e) =>
            onFormChange((prev) => ({
              ...prev,
              url: e.target.value,
            }))
          }
          placeholder="https://example.com/documentation"
        />
      </div>

      <div className="form-row">
        <div className="form-group">
          <label>Max Depth</label>
          <input
            type="number"
            value={form.max_depth}
            onChange={(e) =>
              onFormChange((prev) => ({
                ...prev,
                max_depth: parseInt(e.target.value, 10) || 2,
              }))
            }
            min="1"
            max="5"
          />
        </div>
        <div className="form-group">
          <label>Crawler</label>
          <select
            value={form.crawler}
            className="coreui-select"
            onChange={(e) =>
              onFormChange((prev) => ({
                ...prev,
                crawler: e.target.value,
              }))
            }
          >
            <option value="playwright">Playwright</option>
          </select>
        </div>
      </div>

      <div className="form-group">
        <label>
          <input
            type="checkbox"
            checked={form.doc_only}
            onChange={(e) =>
              onFormChange((prev) => ({
                ...prev,
                doc_only: e.target.checked,
              }))
            }
          />
          Doc Only (restrict to documentation pages)
        </label>
      </div>

      <div className="form-group">
        <label>Seed URLs (optional)</label>
        <SeedUrlsEditor
          seedUrls={form.seed_urls}
          onChange={(seedUrls) =>
            onFormChange((prev) => ({
              ...prev,
              seed_urls: seedUrls,
            }))
          }
        />
      </div>
    </ModalShell>
  );
}
