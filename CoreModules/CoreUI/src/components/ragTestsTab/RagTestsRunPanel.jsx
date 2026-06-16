import React from 'react';
import Card from '../Card';
import CoreUIButton from '../CoreUIButton';
import CoreUISlider from '../CoreUISlider';
import { confirmCloudRagRun, sortModelsCloudFirst } from './helpers';

export default function RagTestsRunPanel(props) {
  const {
    models,
    selectedProviderId,
    setSelectedProviderId,
    providerCatalog,
    selectedModel,
    setSelectedModel,
    collections,
    selectedCollection,
    setSelectedCollection,
    prompts,
    selectedPromptName,
    setSelectedPromptName,
    runConcurrency,
    setRunConcurrency,
    runStrictMode,
    setRunStrictMode,
    runTemperature,
    setRunTemperature,
    runTopK,
    setRunTopK,
    canRun,
    runAllDisabled,
    runFilteredDisabled,
    runSelectedDisabled,
    hasSelectedTests,
    hasActiveFilters,
    handleRunAll,
    handleRunFiltered,
    handleRunSelected,
    running,
    runProgress,
    handleCancelRun,
    error,
    runError,
    setCreateOpen,
  } = props;
  return (
    <>
      <div className="rag-tests-header">
        <h2>RAG Tests</h2>
        {!running && (
          <CoreUIButton variant="primary" onClick={() => setCreateOpen(true)}>
            Create test
          </CoreUIButton>
        )}
      </div>

      {!running && (
        <div className="rag-tests-run-controls">
          <Card className="rag-tests-control-card rag-tests-control-card-wide">
            <div className="rag-tests-control-card-copy">
              <h3>Model & collection</h3>
              <p>Select the answering model, the RAG collection used for retrieval, and the prompt/concurrency for this run.</p>
            </div>
            <div className="rag-tests-control-grid">
              <label className="rag-tests-model-label">
                Provider
                <select
                  value={selectedProviderId}
                  onChange={(e) => {
                    const nextProviderId = e.target.value;
                    setSelectedProviderId(nextProviderId);
                    const nextModels = sortModelsCloudFirst(
                      (providerCatalog.models || []).filter(
                        (m) => m.provider_id === nextProviderId,
                      ),
                    );
                    setSelectedModel(nextModels[0]?.id || '');
                  }}
                  className="rag-tests-select"
                  aria-label="Select provider"
                >
                  {providerCatalog.providers.map((provider) => (
                    <option key={provider.provider_id} value={provider.provider_id}>
                      {provider.title || provider.provider_id}
                    </option>
                  ))}
                </select>
              </label>
              <label className="rag-tests-model-label">
                Model
                <select
                  value={selectedModel}
                  onChange={(e) => setSelectedModel(e.target.value)}
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
                  disabled={collections.length === 0}
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
            </div>
            {collections.length === 0 && (
              <span className="rag-tests-no-collections-hint">
                No collections. Create one in Crawler / RAG then come back.
              </span>
            )}
          </Card>

          <Card className="rag-tests-control-card rag-tests-strict-card">
            <div className="rag-tests-control-card-copy">
              <h3>Strict Mode</h3>
              <p>Requires an exact <code>RAG QUOTE</code> from retrieved context. Use it to test grounding/retrieval, not general answer quality.</p>
            </div>
            <label className="rag-tests-checkbox-label rag-tests-strict-toggle">
              <input
                type="checkbox"
                checked={runStrictMode}
                onChange={(e) => setRunStrictMode(e.target.checked)}
              />
              Strict Mode
            </label>
          </Card>

          <Card className="rag-tests-control-card rag-tests-tuning-card">
            <div className="rag-tests-control-card-copy">
              <h3>Generation tuning</h3>
              <p>Temperature changes answer variability. Top K controls how many retrieved chunks are offered to the model.</p>
            </div>
            <div className="rag-tests-slider-row">
              <CoreUISlider
                label="Temperature"
                valueText={Number(runTemperature).toFixed(1)}
                min="0"
                max="2"
                step="0.1"
                value={runTemperature}
                onChange={(e) => setRunTemperature(Number(e.target.value))}
                aria-label="RAG tests temperature"
              />
              <CoreUISlider
                label="Top K"
                valueText={Number(runTopK).toFixed(1)}
                min="0.1"
                max="30"
                step="0.1"
                value={runTopK}
                onChange={(e) => setRunTopK(Number(e.target.value))}
                aria-label="RAG tests top k"
              />
            </div>
          </Card>

          <div className="rag-tests-run-actions">
            <CoreUIButton
              variant="primary"
              onClick={handleRunAll}
              disabled={runAllDisabled}
              title={hasSelectedTests ? 'Clear selected tests to run all' : hasActiveFilters ? 'Clear filters to run all' : undefined}
            >
              Run all
            </CoreUIButton>
            <CoreUIButton
              onClick={handleRunFiltered}
              disabled={runFilteredDisabled}
              title={hasSelectedTests ? 'Clear selected tests to run filtered' : !hasActiveFilters ? 'Choose a filter first' : undefined}
            >
              Run filtered
            </CoreUIButton>
            <CoreUIButton
              onClick={handleRunSelected}
              disabled={runSelectedDisabled}
              title={!hasSelectedTests ? 'Select one or more tests first' : undefined}
            >
              Run selected
            </CoreUIButton>
          </div>
        </div>
      )}

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

    </>
  );
}
