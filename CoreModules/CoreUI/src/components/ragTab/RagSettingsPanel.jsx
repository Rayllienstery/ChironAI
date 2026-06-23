import React from 'react';
import Card from '../Card';
import { ADVANCED_RETRIEVAL_OPTIONS } from './constants';

export default function RagSettingsPanel({
  ragModelSettings,
  setRagModelSettings,
  ragModelDefaults,
  retrievalYamlDefaults,
  embedProviders,
  filteredEmbedModels,
  rerankProviders,
  filteredRerankModels,
  ragModelSaving,
  ragModelSaveNotice,
  handleSaveRagModelSettings,
  triggerSettings,
  triggerThresholdDraft,
  setTriggerThresholdDraft,
  triggerSaving,
  handleSaveTriggerThreshold,
  triggerTestMessage,
  setTriggerTestMessage,
  triggerTestResult,
  triggerTestLoading,
  handleCheckTrigger,
  overlappingWords,
  collections,
  keywordCollections,
  sheetOpen,
  setSheetOpen,
  llmProxyRagSelect,
  setLlmProxyRagSelect,
  qdrantCollectionNames,
  bindingsNotice,
  savingLlmRagBinding,
  saveLlmProxyRagBinding,
  frameworkSettings,
  frameworkTtlDraft,
  setFrameworkTtlDraft,
  savingFrameworkSettings,
  busy,
  handleSaveFrameworkSettings,
}) {
  return (
        <>
          <Card
            id="rag-qdrant-models-section"
            className="rag-trigger-card"
            aria-label="RAG embedding model settings"
          >
            <h3 className="rag-trigger-card-title">Embedding model (index + query)</h3>
            <p className="rag-trigger-card-description">
              Embedding model affects how chunks are encoded into Qdrant.
              If you change the embedding model, you typically need to re-create Qdrant collections (vector dimension may differ).
            </p>

            <div className="rag-trigger-threshold-row">
              <label className="rag-trigger-label" htmlFor="rag-embed-provider">Provider</label>
              <select
                id="rag-embed-provider"
                className="rag-trigger-input"
                value={ragModelSettings.rag_embed_provider_id}
                onChange={(e) =>
                  setRagModelSettings((prev) => ({
                    ...prev,
                    rag_embed_provider_id: e.target.value,
                    rag_embed_model: '',
                  }))
                }
                disabled={!embedProviders.length}
              >
                <option value="">
                  Server default provider ({ragModelDefaults.rag_embed_provider_id || 'not configured'})
                </option>
                {embedProviders.map((provider) => (
                  <option key={provider.provider_id} value={provider.provider_id}>
                    {provider.title || provider.provider_id}
                  </option>
                ))}
              </select>
            </div>
            <div className="rag-trigger-threshold-row">
              <label className="rag-trigger-label" htmlFor="rag-embed-model">Model</label>
              <select
                id="rag-embed-model"
                className="rag-trigger-input"
                value={ragModelSettings.rag_embed_model}
                onChange={(e) => setRagModelSettings((prev) => ({ ...prev, rag_embed_model: e.target.value }))
                }
                disabled={!filteredEmbedModels.length}
              >
                <option value="">
                  Server default ({ragModelDefaults.rag_embed_model || 'not configured'})
                </option>
                {ragModelSettings.rag_embed_model &&
                  !filteredEmbedModels.some((m) => m.id === ragModelSettings.rag_embed_model) && (
                    <option value={ragModelSettings.rag_embed_model}>
                      {ragModelSettings.rag_embed_model} (saved — not in current provider list)
                    </option>
                  )}
                {filteredEmbedModels.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
            <p className="rag-trigger-hint rag-trigger-hint--tight">
              Empty selection uses the server default above (from env <code>RAG_EMBED_MODEL</code> or{' '}
              <code>config/models.yaml</code>).
            </p>

            <div className="rag-trigger-actions">
              <button
                type="button"
                className="rag-button primary"
                onClick={handleSaveRagModelSettings}
                disabled={busy || ragModelSaving}
              >
                {ragModelSaving ? 'Saving…' : 'Save embedding settings'}
              </button>
              {ragModelSaveNotice && (
                <p className={`rag-model-save-notice rag-model-save-notice--${ragModelSaveNotice.type}`}>
                  {ragModelSaveNotice.text}
                </p>
              )}
            </div>
          </Card>

          <Card className="rag-trigger-card" aria-label="Hybrid sparse settings">
            <h3 className="rag-trigger-card-title">Hybrid sparse (dense + keyword)</h3>
            <p className="rag-trigger-card-description">
              One setting for both <strong>indexing new collections</strong> (writes dense + sparse vectors to Qdrant)
              and <strong>retrieval</strong> (RRF fusion when the collection has sparse data).
            </p>
            <div className="rag-trigger-threshold-row">
              <label className="rag-trigger-inline-check">
                <input
                  type="checkbox"
                  id="rag-hybrid-sparse-enabled"
                  checked={ragModelSettings.hybrid_sparse_enabled}
                  onChange={(e) =>
                    setRagModelSettings((prev) => ({ ...prev, hybrid_sparse_enabled: e.target.checked }))
                  }
                />
                Enabled
              </label>
            </div>
            <p className="rag-trigger-hint rag-trigger-hint--tight">
              Turn off for legacy dense-only collections or to skip sparse encoding. Config default:{' '}
              {ragModelDefaults.hybrid_sparse_enabled ? 'on' : 'off'} (from <code>retrieval.yaml</code> if never saved).
            </p>
            <div className="rag-trigger-actions">
              <button
                type="button"
                className="rag-button primary"
                onClick={handleSaveRagModelSettings}
                disabled={busy || ragModelSaving}
              >
                {ragModelSaving ? 'Saving…' : 'Save hybrid settings'}
              </button>
              {ragModelSaveNotice && (
                <p className={`rag-model-save-notice rag-model-save-notice--${ragModelSaveNotice.type}`}>
                  {ragModelSaveNotice.text}
                </p>
              )}
            </div>
          </Card>

          <Card className="rag-trigger-card" aria-label="Rerank model settings">
            <h3 className="rag-trigger-card-title">Rerank for RAG</h3>
            <p className="rag-trigger-card-description">
              Rerank affects how retrieved chunks are ordered before they go into the final prompt.
            </p>
            <div className="rag-trigger-threshold-row">
              <label className="rag-trigger-inline-check">
                <input
                  type="checkbox"
                  checked={ragModelSettings.rerank_for_rag}
                  onChange={(e) => setRagModelSettings((prev) => ({ ...prev, rerank_for_rag: e.target.checked }))}
                />
                Enabled
              </label>
            </div>

            <div className="rag-trigger-threshold-row">
              <label className="rag-trigger-label" htmlFor="rag-rerank-provider">Rerank provider</label>
              <select
                id="rag-rerank-provider"
                className="rag-trigger-input"
                value={ragModelSettings.rag_rerank_provider_id}
                onChange={(e) =>
                  setRagModelSettings((prev) => ({
                    ...prev,
                    rag_rerank_provider_id: e.target.value,
                    rerank_model: '',
                  }))
                }
                disabled={!rerankProviders.length}
              >
                <option value="">
                  Server default provider ({ragModelDefaults.rag_rerank_provider_id || 'not configured'})
                </option>
                {rerankProviders.map((provider) => (
                  <option key={provider.provider_id} value={provider.provider_id}>
                    {provider.title || provider.provider_id}
                  </option>
                ))}
              </select>
            </div>
            <div className="rag-trigger-threshold-row">
              <label className="rag-trigger-label" htmlFor="rag-rerank-model">Rerank model</label>
              <select
                id="rag-rerank-model"
                className="rag-trigger-input"
                value={ragModelSettings.rerank_model}
                onChange={(e) => setRagModelSettings((prev) => ({ ...prev, rerank_model: e.target.value }))
                }
                disabled={!filteredRerankModels.length}
              >
                <option value="">
                  Server default ({ragModelDefaults.rerank_model || 'not configured'}) — used when rerank is enabled and no model is chosen
                </option>
                {ragModelSettings.rerank_model &&
                  !filteredRerankModels.some((m) => m.id === ragModelSettings.rerank_model) && (
                    <option value={ragModelSettings.rerank_model}>
                      {ragModelSettings.rerank_model} (saved — not in current provider list)
                    </option>
                  )}
                {filteredRerankModels.map((m) => (
                  <option key={m.id} value={m.id}>{m.name}</option>
                ))}
              </select>
            </div>
            <p className="rag-trigger-hint rag-trigger-hint--tight">
              Empty selection uses the server default above (from env <code>RAG_RERANK_MODEL</code> or{' '}
              <code>config/models.yaml</code>).
            </p>
            <div className="rag-trigger-actions">
              <button
                type="button"
                className="rag-button primary"
                onClick={handleSaveRagModelSettings}
                disabled={busy || ragModelSaving}
              >
                {ragModelSaving ? 'Saving…' : 'Save rerank settings'}
              </button>
              {ragModelSaveNotice && (
                <p className={`rag-model-save-notice rag-model-save-notice--${ragModelSaveNotice.type}`}>
                  {ragModelSaveNotice.text}
                </p>
              )}
            </div>
          </Card>

          <Card className="rag-trigger-card" aria-label="Advanced retrieval options">
            <h3 className="rag-trigger-card-title">Advanced retrieval options</h3>
            <p className="rag-adv-retrieval-intro">
              Fine-tune how the RAG pipeline selects and formats context. These settings are saved to your local profile and override <code>retrieval.yaml</code> defaults.
            </p>
            <div className="rag-adv-options-list">
              {ADVANCED_RETRIEVAL_OPTIONS.map((opt) => (
                <div key={opt.key} className="rag-adv-option">
                  <div className="rag-adv-option-head">
                    <label>
                      <input
                        type="checkbox"
                        checked={Boolean(ragModelSettings[opt.key])}
                        onChange={(e) =>
                          setRagModelSettings((prev) => ({ ...prev, [opt.key]: e.target.checked }))
                        }
                      />
                      {opt.label}
                    </label>
                    <span className={`rag-adv-cost rag-adv-cost--${opt.cost}`}>
                      {opt.costLabel}
                    </span>
                  </div>
                  <div className="rag-adv-option-body">
                    {opt.lines.map((line, i) => (
                      <span key={i} className="rag-adv-option-line">
                        <strong>{line.tag}:</strong> {line.text}
                      </span>
                    ))}
                    <span className="rag-adv-yaml-hint">
                      YAML default: {retrievalYamlDefaults[opt.key] ? 'on' : 'off'}
                    </span>
                  </div>
                </div>
              ))}
            </div>
            <div className="rag-trigger-actions">
              <button
                type="button"
                className="rag-button primary"
                onClick={handleSaveRagModelSettings}
                disabled={busy || ragModelSaving}
              >
                {ragModelSaving ? 'Saving…' : 'Save advanced options'}
              </button>
              {ragModelSaveNotice && (
                <p className={`rag-model-save-notice rag-model-save-notice--${ragModelSaveNotice.type}`}>
                  {ragModelSaveNotice.text}
                </p>
              )}
            </div>
          </Card>


          <section
            id="rag-consumer-bindings-section"
            className="rag-service-bindings-card"
            aria-labelledby="rag-service-bindings-heading"
          >
            <h3 id="rag-service-bindings-heading">Service bindings</h3>
            <p className="rag-service-bindings-intro">
              Choose which Qdrant collection each runtime consumer uses. Empty selection means the server config default (
              <code>qdrant.collection_name</code>).
            </p>
            {bindingsNotice && (
              <p
                className={
                  bindingsNotice.type === 'error' ? 'rag-service-bindings-notice error' : 'rag-service-bindings-notice'
                }
                role={bindingsNotice.type === 'error' ? 'alert' : 'status'}
              >
                {bindingsNotice.text}
              </p>
            )}
            <div className="rag-service-bindings-grid">
              <div className="rag-service-binding-row">
                <label className="rag-service-binding-label" htmlFor="rag-binding-llm-proxy">
                  LLM Proxy (OpenAI / Anthropic RAG)
                </label>
                <div className="rag-service-binding-controls">
                  <select
                    id="rag-binding-llm-proxy"
                    className="rag-service-binding-select"
                    value={
                      qdrantCollectionNames.length > 0 && qdrantCollectionNames.includes((llmProxyRagSelect || '').trim())
                        ? llmProxyRagSelect
                        : ''
                    }
                    onChange={(e) => setLlmProxyRagSelect(e.target.value)}
                    disabled={collections.length === 0}
                    aria-label="Qdrant collection for LLM Proxy"
                  >
                    <option value="">
                      {collections.length === 0
                        ? 'No collections — create one below or crawl/index first'
                        : 'Config default'}
                    </option>
                    {collections.map((col) => (
                      <option key={col.name} value={col.name}>
                        {col.name}
                        {col.points_count != null ? ` (${col.points_count} vectors)` : ''}
                      </option>
                    ))}
                  </select>
                  <button
                    type="button"
                    className="rag-button primary"
                    onClick={saveLlmProxyRagBinding}
                    disabled={savingLlmRagBinding || busy}
                  >
                    {savingLlmRagBinding ? 'Saving…' : 'Save'}
                  </button>
                </div>
                {(llmProxyRagSelect || '').trim() &&
                  qdrantCollectionNames.length > 0 &&
                  !qdrantCollectionNames.includes((llmProxyRagSelect || '').trim()) && (
                    <p className="rag-service-binding-stale">
                      Database has <code>{llmProxyRagSelect}</code> (not in current Qdrant list) — pick a listed collection or
                      clear to default.
                    </p>
                  )}
              </div>
            </div>
          </section>


          <Card
            className="rag-keywords-card"
            role="button"
            tabIndex={0}
            onClick={() => setSheetOpen(true)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                setSheetOpen(true);
              }
            }}
            elevateOnHover
            aria-label="Manage keywords that trigger RAG search"
          >
            <h3 className="rag-keywords-card-title">Keywords that trigger RAG search</h3>
            <div className="rag-keywords-collections-row">
              {keywordCollections.filter((c) => c.enabled).length === 0 ? (
                <span className="rag-keywords-collections-empty">No active collections</span>
              ) : (
                keywordCollections
                  .filter((c) => c.enabled)
                  .map((c) => (
                    <div key={c.id} className="rag-keywords-collection-chip">
                      <span className="rag-keywords-collection-chip-name">{c.name}:</span>
                      <span className="rag-keywords-collection-chip-meta">
                        {(c.keywords || []).length} word{(c.keywords || []).length !== 1 ? 's' : ''}
                      </span>
                    </div>
                  ))
              )}
            </div>
            <p className="rag-keywords-card-description">
              Matching is case-insensitive: the user query is compared in lower case.
              RAG is also triggered by technical signals (e.g. CamelCase, code blocks, technical phrases) when the trigger score is high enough.
            </p>
            {overlappingWords.length > 0 && (
              <div className="rag-keywords-card-warning">
                Duplicated in collections: {overlappingWords.join(', ')}
              </div>
            )}
            <button
              type="button"
              className="rag-button primary rag-keywords-card-action"
              onClick={(e) => { e.stopPropagation(); setSheetOpen(true); }}
            >
              Manage keywords
            </button>
          </Card>

          <Card className="rag-trigger-card" elevation="var(--md-sys-elevation-level1)">
            <h3 className="rag-trigger-card-title">RAG trigger threshold</h3>
            <p className="rag-trigger-card-description">
              RAG runs when the message score is at least this value. Score is the sum of signals below.
            </p>
            <div className="rag-trigger-threshold-row">
              <label className="rag-trigger-label" htmlFor="rag-trigger-threshold">
                Threshold
              </label>
              <input
                id="rag-trigger-threshold"
                type="number"
                min={0}
                max={20}
                value={triggerThresholdDraft}
                onChange={(e) => setTriggerThresholdDraft(e.target.value)}
                className="rag-trigger-input"
                aria-describedby="rag-trigger-threshold-desc"
              />
              <button
                type="button"
                className="rag-button primary"
                onClick={handleSaveTriggerThreshold}
                disabled={
                  triggerSaving ||
                  (() => {
                    const v = parseInt(triggerThresholdDraft, 10);
                    const valid = !Number.isNaN(v) && v >= 0 && v <= 20;
                    const unchanged = String(triggerSettings?.rag_trigger_threshold ?? '') === triggerThresholdDraft;
                    return !valid || unchanged;
                  })()
                }
              >
                {triggerSaving ? 'Saving…' : 'Save'}
              </button>
            </div>
            <p id="rag-trigger-threshold-desc" className="rag-trigger-hint">
              Value 0–20. Saved in app settings (overrides config).
            </p>
            <div className="rag-trigger-table-wrap">
              <table className="rag-trigger-table" aria-label="How trigger score is computed">
                <thead>
                  <tr>
                    <th>Signal</th>
                    <th>Points</th>
                  </tr>
                </thead>
                <tbody>
                  {(triggerSettings?.trigger_help_table || []).map((row, i) => (
                    <tr key={i}>
                      <td>{row.signal}</td>
                      <td>{row.points}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="rag-trigger-test">
              <h4 className="rag-trigger-test-title">Test message</h4>
              <p className="rag-trigger-test-desc">Enter a message to see whether it would trigger RAG.</p>
              <textarea
                className="rag-trigger-test-input"
                value={triggerTestMessage}
                onChange={(e) => setTriggerTestMessage(e.target.value)}
                placeholder="e.g. How does SwiftUI work?"
                rows={2}
                aria-label="Message to test RAG trigger"
              />
              <button
                type="button"
                className="rag-button primary"
                onClick={handleCheckTrigger}
                disabled={triggerTestLoading}
              >
                {triggerTestLoading ? 'Checking…' : 'Check'}
              </button>
              {triggerTestResult != null && (
                <div className="rag-trigger-test-result" role="status">
                  <p className="rag-trigger-test-summary">
                    <strong>RAG {triggerTestResult.triggered ? 'will run' : 'will not run'}</strong>
                    {' — '}
                    score <strong>{triggerTestResult.score}</strong>
                    {triggerTestResult.signals?.length > 0
                      ? ` (${triggerTestResult.signals.join(', ')})`
                      : ''}
                    , threshold {triggerTestResult.threshold}.
                  </p>
                </div>
              )}
            </div>
          </Card>

          <Card className="rag-trigger-card" elevation="var(--md-sys-elevation-level1)">
            <h3 className="rag-trigger-card-title">Framework docs versioning</h3>
            <p className="rag-trigger-card-description">
              Configure how long the latest framework documentation collections (e.g. Alamofire_x.m.n_latest) stay fresh
              before being re-fetched and re-indexed.
            </p>
            <div className="rag-trigger-threshold-row">
              <label className="rag-trigger-label" htmlFor="framework-latest-ttl-days">
                Latest TTL (days)
              </label>
              <input
                id="framework-latest-ttl-days"
                type="number"
                min={1}
                max={3650}
                value={frameworkTtlDraft}
                onChange={(e) => setFrameworkTtlDraft(e.target.value)}
                className="rag-trigger-input"
              />
              <button
                type="button"
                className="rag-button primary"
                onClick={handleSaveFrameworkSettings}
                disabled={busy || savingFrameworkSettings}
              >
                {savingFrameworkSettings ? 'Saving…' : 'Save'}
              </button>
            </div>
          </Card>
        </>
  );
}
