import React, { useEffect, useState } from 'react';
import { getRagStatus, getRagCollections, startRag, stopRag } from '../services/api';
import './RagTab.css';

function RagTab() {
  const [loading, setLoading] = useState(true);
  const [status, setStatus] = useState(null);
  const [collections, setCollections] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

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

  useEffect(() => {
    loadStatus();
    loadCollections();
  }, []);

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

  return (
    <div className="rag-tab">
      <div className="rag-header">
        <h2>RAG / Qdrant</h2>
        <div className="rag-actions">
          <span className={`rag-status-badge ${isRunning ? 'running' : 'stopped'}`}>
            {isRunning ? 'Running' : 'Stopped'}
          </span>
          <button
            type="button"
            className="rag-button primary"
            onClick={handleStart}
            disabled={busy || isRunning}
          >
            Start
          </button>
          <button
            type="button"
            className="rag-button"
            onClick={handleStop}
            disabled={busy || !isRunning}
          >
            Stop
          </button>
          <button
            type="button"
            className="rag-button ghost"
            onClick={() => {
              loadStatus();
              loadCollections();
            }}
            disabled={busy}
          >
            Refresh
          </button>
        </div>
      </div>

      {status && (
        <div className="rag-status-grid">
          <div className="rag-status-card">
            <div className="label">Endpoint</div>
            <div className="value">{status.url}</div>
          </div>
          <div className="rag-status-card">
            <div className="label">Running</div>
            <div className="value">{status.running ? 'Yes' : 'No'}</div>
          </div>
          <div className="rag-status-card">
            <div className="label">Collections</div>
            <div className="value">{status.collections_count ?? '—'}</div>
          </div>
          {status.version && (
            <div className="rag-status-card">
              <div className="label">Version</div>
              <div className="value">{status.version}</div>
            </div>
          )}
        </div>
      )}

      {error && <div className="rag-error">Error: {error}</div>}

      <div className="rag-collections">
        <div className="collections-header">
          <h3>Collections</h3>
        </div>
        {loading ? (
          <div className="loading">Checking Qdrant status...</div>
        ) : !collections.length ? (
          <div className="empty-state">No collections found or Qdrant is not reachable.</div>
        ) : (
          <table className="collections-table">
            <thead>
              <tr>
                <th>Name</th>
                <th>Vectors</th>
                <th>Shards</th>
                <th>Replication</th>
                <th>On Disk</th>
              </tr>
            </thead>
            <tbody>
              {collections.map((col) => (
                <tr key={col.name}>
                  <td>{col.name}</td>
                  <td>{col.points_count ?? '—'}</td>
                  <td>{col.shards_count ?? '—'}</td>
                  <td>{col.replication_factor ?? '—'}</td>
                  <td>{col.on_disk ? 'Yes' : 'No'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default RagTab;
