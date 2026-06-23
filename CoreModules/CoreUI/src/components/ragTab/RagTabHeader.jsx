import React from 'react';

export default function RagTabHeader({
  isRunning,
  busy,
  status,
  onRefresh,
  onStartStop,
  onOpenDashboard,
}) {
  return (
      <div className="rag-header">
        <h2>RAG / Qdrant</h2>
        <div className="rag-actions">
          <div className={`rag-status-badge ${isRunning ? 'running' : 'stopped'}`}>
            {isRunning ? 'Running' : 'Stopped'}
            <button
              type="button"
              className="rag-refresh-btn"
              onClick={onRefresh}
              disabled={busy}
              title="Refresh status"
            >
              <span className="material-symbols-outlined">refresh</span>
            </button>
          </div>
          <button
            type="button"
            className={`coreui-btn ${isRunning ? '' : 'coreui-btn-primary'}`}
            onClick={onStartStop}
            disabled={busy}
          >
            {isRunning ? 'Stop' : 'Start'}
          </button>
          <button
            type="button"
            className="coreui-btn coreui-btn-ghost"
            onClick={onOpenDashboard}
            disabled={!status?.url}
            title="Open Qdrant Dashboard in new tab"
          >
            Open Dashboard
          </button>
        </div>
      </div>

  );
}
