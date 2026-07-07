import CreateCollectionIndexProgress from "./CreateCollectionIndexProgress";
import { FieldLabelWithHelp } from "./common/InfoButton.jsx";
import { t } from "../services/i18n.js";

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
            aria-label={t("common.close")}
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
        {t("crawler.modal.add_seed_url")}
      </button>
      <div className="form-hint">
        {t("crawler.modal.seed_urls_hint")}
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
    <ModalShell title={t("crawler.pipeline.create_title")} onClose={onClose}>
      <label className="indexer-select-label">
        {t("crawler.pipeline.name_label")}
        <input
          type="text"
          value={newPipelineName}
          onChange={(e) => onChangeName(e.target.value)}
          className="md-pipeline-param-input"
          placeholder={t("crawler.pipeline.name_placeholder")}
          onKeyDown={(e) => e.key === "Enter" && onConfirm()}
        />
      </label>
      <div className="md-pipeline-modal-actions">
        <button type="button" className="crawler-button primary" onClick={onConfirm}>
          {t("crawler.pipeline.create_btn")}
        </button>
        <button type="button" className="crawler-button ghost" onClick={onClose}>
          {t("common.cancel")}
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
      title={t("crawler.pipeline.delete_title")}
      onClose={onClose}
      className="md-pipeline-delete-confirm"
    >
      <p className="md-pipeline-delete-message">
        {t("crawler.pipeline.delete_message", { name: pipelineName })}
      </p>
      <div className="md-pipeline-modal-actions">
        <button type="button" className="crawler-button" onClick={onClose}>
          {t("common.cancel")}
        </button>
        <button
          type="button"
          className="crawler-button primary danger"
          onClick={onConfirm}
        >
          {t("crawler.pipeline.delete_btn")}
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
      title={t("crawler.modal.create_collection_title")}
      onClose={onClose}
      closeDisabled={isRunning}
      className={`create-collection-modal${isRunning ? " create-collection-modal--running" : ""}`}
      footer={
        isRunning ? (
          <button
            type="button"
            className="crawler-button"
            onClick={onCancelCreate}
            disabled={createCanceling}
          >
            {createCanceling ? t("crawler.modal.cancelling_indexing") : t("crawler.modal.cancel_indexing")}
          </button>
        ) : (
          <>
            <button
              type="button"
              className="crawler-button"
              onClick={onClose}
            >
              {t("common.cancel")}
            </button>
            <button
              type="button"
              className="crawler-button primary"
              onClick={onCreate}
            >
              {t("crawler.modal.create_collection_btn")}
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
                t("crawler.modal.collection_failed")}
            </div>
          )}
          <CreateCollectionIndexProgress
            progress={createProgress}
            collectionName={createForm.collection_name || t("crawler.modal.collection_default_name")}
            variant="modal"
          />
        </div>
      )}
      {isRunning ? null : (
        <>
      <div className="form-group">
        <label>
          <FieldLabelWithHelp helpRef="indexing#create-collection" helpLabel={t("crawler.modal.collection_name")}>
            {t("crawler.modal.collection_name")} *
          </FieldLabelWithHelp>
        </label>
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
      <div className="form-group" data-tour="crawler-collection-embed">
        <label htmlFor="create-collection-embed-provider">
          <FieldLabelWithHelp helpRef="indexing#embedding" helpLabel={t("crawler.modal.embed_provider")}>
            {t("crawler.modal.embed_provider")}
          </FieldLabelWithHelp>
        </label>
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
            {t("crawler.modal.select_provider")}
          </option>
          {embedProviderOptions.map((provider) => (
            <option key={provider.provider_id} value={provider.provider_id}>
              {provider.title || provider.provider_id}
            </option>
          ))}
        </select>
      </div>
      <div className="form-group">
        <label htmlFor="create-collection-embed-model">
          <FieldLabelWithHelp helpRef="indexing#embedding" helpLabel={t("crawler.modal.embed_model")}>
            {t("crawler.modal.embed_model")}
          </FieldLabelWithHelp>
        </label>
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
              ? t("crawler.modal.select_model")
              : t("crawler.modal.select_provider_first")}
          </option>
          {createForm.rag_embed_model &&
            !filteredEmbedModels.some((m) => m.id === createForm.rag_embed_model) && (
              <option value={createForm.rag_embed_model}>
                {t("crawler.modal.saved_model_suffix", {
                  model: createForm.rag_embed_model,
                })}
              </option>
            )}
          {filteredEmbedModels.map((m) => (
            <option key={m.id} value={m.id}>
              {m.name || m.id}
            </option>
          ))}
        </select>
        <p className="create-collection-embed-hint">
          {t("crawler.modal.embed_hint")}
        </p>
      </div>
      <div className="form-group">
        <label htmlFor="create-collection-parallel-workers">
          <FieldLabelWithHelp helpRef="indexing#embedding#parallel" helpLabel={t("crawler.modal.parallel_workers")}>
            {t("crawler.modal.parallel_workers")}
          </FieldLabelWithHelp>
        </label>
        <input
          id="create-collection-parallel-workers"
          type="number"
          value={createForm.parallel_embed_workers ?? 4}
          onChange={(e) =>
            onFormChange((prev) => {
              const parsed = parseInt(e.target.value, 10);
              const workers = Number.isFinite(parsed)
                ? Math.min(8, Math.max(1, parsed))
                : 4;
              return {
                ...prev,
                parallel_embed_workers: workers,
              };
            })
          }
          min="1"
          max="8"
          step="1"
          disabled={creating}
        />
        <p className="create-collection-embed-hint">
          {t("crawler.modal.parallel_workers_hint")}
        </p>
      </div>
      <div className="form-group">
        <label>
          <FieldLabelWithHelp helpRef="indexing#sources" helpLabel={t("crawler.modal.select_sources")}>
            {t("crawler.modal.select_sources")} *
          </FieldLabelWithHelp>
        </label>
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
      <div className="form-row" data-tour="crawler-collection-chunking">
        <div className="form-group">
          <label>
            <FieldLabelWithHelp helpRef="indexing#chunking" helpLabel={t("crawler.modal.chunk_max")}>
              {t("crawler.modal.chunk_max")}
            </FieldLabelWithHelp>
          </label>
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
          <label>
            <FieldLabelWithHelp helpRef="indexing#chunking" helpLabel={t("crawler.modal.chunk_min")}>
              {t("crawler.modal.chunk_min")}
            </FieldLabelWithHelp>
          </label>
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
          <label>
            <FieldLabelWithHelp helpRef="indexing#chunking" helpLabel={t("crawler.modal.confidence_threshold")}>
              {t("crawler.modal.confidence_threshold")}
            </FieldLabelWithHelp>
          </label>
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
          <label>
            <FieldLabelWithHelp helpRef="indexing#chunking" helpLabel={t("crawler.modal.top_k")}>
              {t("crawler.modal.top_k")}
            </FieldLabelWithHelp>
          </label>
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
      title={
        isEdit
          ? t("crawler.modal.edit_source_title", { id: sourceId })
          : t("crawler.modal.add_source_title")
      }
      onClose={onClose}
      footer={
        <>
          <button
            type="button"
            className="crawler-button"
            onClick={onClose}
            disabled={loading}
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            className="crawler-button primary"
            onClick={onSubmit}
            disabled={loading}
          >
            {loading
              ? isEdit
                ? t("crawler.modal.updating")
                : t("crawler.modal.adding")
              : isEdit
                ? t("crawler.modal.update_source_btn")
                : t("crawler.modal.add_source_btn")}
          </button>
        </>
      }
    >
      {isEdit ? (
        <div className="form-group">
          <label>{t("crawler.modal.source_id")}</label>
          <input
            type="text"
            value={form.id}
            disabled
            className="crawler-input-disabled"
          />
          <div className="form-hint">{t("crawler.modal.source_id_immutable")}</div>
        </div>
      ) : (
        <div className="form-group">
          <label>
            <FieldLabelWithHelp helpRef="indexing#sources" helpLabel={t("crawler.modal.source_id")}>
              {t("crawler.modal.source_id")} *
            </FieldLabelWithHelp>
          </label>
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
          <div className="form-hint">{t("crawler.modal.source_id_hint")}</div>
        </div>
      )}

      <div className="form-group">
        <label>
          <FieldLabelWithHelp helpRef="indexing#sources" helpLabel={t("crawler.modal.url")}>
            {t("crawler.modal.url")} *
          </FieldLabelWithHelp>
        </label>
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
          <label>
            <FieldLabelWithHelp helpRef="indexing#sources" helpLabel={t("crawler.modal.max_depth")}>
              {t("crawler.modal.max_depth")}
            </FieldLabelWithHelp>
          </label>
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
          <label>
            <FieldLabelWithHelp helpRef="indexing#sources" helpLabel={t("crawler.modal.crawler_engine")}>
              {t("crawler.modal.crawler_engine")}
            </FieldLabelWithHelp>
          </label>
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
            <option value="playwright">{t("crawler.engine.playwright")}</option>
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
          <FieldLabelWithHelp helpRef="indexing#sources#seed-urls" helpLabel={t("crawler.modal.doc_only")}>
            {t("crawler.modal.doc_only")}
          </FieldLabelWithHelp>
        </label>
      </div>

      <div className="form-group">
        <label>
          <FieldLabelWithHelp helpRef="indexing#sources#seed-urls" helpLabel={t("crawler.modal.seed_urls")}>
            {t("crawler.modal.seed_urls")}
          </FieldLabelWithHelp>
        </label>
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
