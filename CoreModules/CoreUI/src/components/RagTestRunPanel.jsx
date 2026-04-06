import React from 'react';
import Card from './Card';
import '../styles/components/RagTestRunPanel.css';

export function RagTestRunPanelBody({
  running,
  runProgress,
  runError,
  onCancel,
  onGoToRagTests,
}) {
  const progress = runProgress || {};
  const total = progress.total || 0;
  const current = progress.current_index || 0;
  const pct = total ? Math.round((current / total) * 100) : 0;

  return (
    <>
      <div className="rag-test-run-panel-header">
        <span className="rag-test-run-panel-title">
          {running ? (
            <span className="rag-test-run-panel-spinner" aria-hidden="true" />
          ) : null}
          RAG Tests run
        </span>
        <div className="rag-test-run-panel-actions">
          <button
            type="button"
            className="rag-test-run-panel-btn"
            onClick={onGoToRagTests}
            aria-label="Open RAG Tests tab"
          >
            RAG Tests
          </button>
          {running && (
            <button
              type="button"
              className="rag-test-run-panel-btn rag-test-run-panel-cancel"
              onClick={onCancel}
              aria-label="Cancel run"
            >
              Cancel
            </button>
          )}
        </div>
      </div>
      <div className="rag-test-run-panel-body">
        <div className="rag-test-run-panel-count">
          [{current}/{total}]
        </div>
        <p className="rag-test-run-panel-current">
          <span className="rag-test-run-panel-current-label">Current test:</span>{' '}
          {progress.current_test_name || '—'}
        </p>
        <div className="rag-test-run-panel-stats">
          <span className="rag-test-run-panel-stat passed">
            <span className="rag-test-run-panel-stat-value">{progress.passed ?? 0}</span>
            <span className="rag-test-run-panel-stat-label">passed</span>
          </span>
          <span className="rag-test-run-panel-stat failed">
            <span className="rag-test-run-panel-stat-value">{progress.failed ?? 0}</span>
            <span className="rag-test-run-panel-stat-label">failed</span>
          </span>
          <span className="rag-test-run-panel-stat pending">
            <span className="rag-test-run-panel-stat-value">{progress.pending ?? 0}</span>
            <span className="rag-test-run-panel-stat-label">pending</span>
          </span>
        </div>
        {total > 0 && (
          <div className="rag-test-run-panel-bar-wrap" aria-hidden="true">
            <div
              className="rag-test-run-panel-bar-fill"
              style={{ width: `${pct}%` }}
            />
          </div>
        )}
        {runError && (
          <p className="rag-test-run-panel-error" role="alert">
            {runError}
          </p>
        )}
      </div>
    </>
  );
}

function RagTestRunPanel(props) {
  return (
    <Card
      className="rag-test-run-panel rag-test-run-panel--docked"
      role="status"
      aria-live="polite"
      aria-label="RAG tests run progress"
      elevation="var(--md-sys-elevation-level3)"
    >
      <RagTestRunPanelBody {...props} />
    </Card>
  );
}

export default RagTestRunPanel;
