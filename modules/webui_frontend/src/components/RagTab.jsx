import React, { useEffect, useState, useCallback } from 'react';
import {
  getRagStatus,
  getRagCollections,
  startRag,
  stopRag,
  getRagKeywordCollections,
  saveRagKeywordCollections,
  deleteRagKeywordCollection,
  getRagTriggerSettings,
  updateRagTriggerSettings,
  checkRagTrigger,
  getRagFrameworkSettings,
  updateRagFrameworkSettings,
} from '../services/api';
import './RagTab.css';

function wordsInMultipleCollections(collections) {
  const wordToCollections = new Map();
  (collections || []).forEach((c) => {
    const id = c.id;
    (c.keywords || []).forEach((k) => {
      const low = (k || '').toLowerCase().trim();
      if (!low) return;
      if (!wordToCollections.has(low)) wordToCollections.set(low, new Set());
      wordToCollections.get(low).add(id);
    });
  });
  const out = [];
  wordToCollections.forEach((ids, word) => {
    if (ids.size > 1) out.push(word);
  });
  return out;
}

function capitalize(word) {
  const s = (word || '').trim();
  if (!s) return '';
  return s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
}

function RagTab() {
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
  const [frameworkSettingsSaving, setFrameworkSettingsSaving] = useState(false);

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
  }, [loadKeywordCollections, loadTriggerSettings, loadFrameworkSettings]);

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
    setFrameworkSettingsSaving(true);
    setError(null);
    try {
      await updateRagFrameworkSettings({ framework_latest_ttl_days: val });
      setFrameworkSettings((prev) =>
        prev ? { ...prev, framework_latest_ttl_days: val } : { framework_latest_ttl_days: val },
      );
    } catch (e) {
      setError(e.message);
    } finally {
      setFrameworkSettingsSaving(false);
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
              loadKeywordCollections();
              loadTriggerSettings();
              loadFrameworkSettings();
            }}
            disabled={busy}
          >
            Refresh
          </button>
          <button
            type="button"
            className="rag-button ghost"
            onClick={handleOpenDashboard}
            disabled={!status?.url}
            title="Open Qdrant Dashboard in new tab"
          >
            Open Dashboard
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

      <div
        className="rag-keywords-card"
        role="button"
        tabIndex={0}
        onClick={() => setSheetOpen(true)}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setSheetOpen(true); } }}
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
      </div>

      <div className="rag-trigger-card">
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
      </div>

      <div className="rag-trigger-card">
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
            aria-describedby="framework-latest-ttl-days-desc"
          />
          <button
            type="button"
            className="rag-button primary"
            onClick={handleSaveFrameworkSettings}
            disabled={
              frameworkSettingsSaving ||
              (() => {
                const v = parseInt(frameworkTtlDraft, 10);
                const valid = !Number.isNaN(v) && v >= 1 && v <= 3650;
                const unchanged =
                  String(frameworkSettings?.framework_latest_ttl_days ?? '') === frameworkTtlDraft;
                return !valid || unchanged;
              })()
            }
          >
            {frameworkSettingsSaving ? 'Saving…' : 'Save'}
          </button>
        </div>
        <p id="framework-latest-ttl-days-desc" className="rag-trigger-hint">
          Value 1–3650 days. Controls when Alamofire_x.m.n_latest and similar collections will be refreshed from
          GitHub (default 90 days).
        </p>
      </div>

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
          <>
            <table className="collections-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Vectors</th>
                  <th>Segments</th>
                  <th>Shards</th>
                  <th>Replication</th>
                  <th>Vectors Config</th>
                  <th>On Disk</th>
                  <th>Framework</th>
                  <th>Version</th>
                  <th>Last refreshed</th>
                  <th>Type</th>
                  <th>Age vs TTL</th>
                </tr>
              </thead>
              <tbody>
                {collections.map((col) => {
                  const isFramework = Boolean(col.framework_id);
                  const isLatest = isFramework && typeof col.name === 'string' && col.name.endsWith('_latest');
                  const ttlDays = frameworkSettings?.framework_latest_ttl_days ?? 90;
                  let ageLabel = '—';
                  if (col.last_refreshed_at && ttlDays && ttlDays > 0) {
                    const refreshed = new Date(col.last_refreshed_at);
                    if (!Number.isNaN(refreshed.getTime())) {
                      const now = new Date();
                      const diffMs = now - refreshed;
                      const ageDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
                      ageLabel = `${ageDays}d / ${ttlDays}d${ageDays > ttlDays ? ' (stale)' : ''}`;
                    }
                  }
                  return (
                    <tr key={col.name}>
                      <td>{col.name}</td>
                      <td>{col.points_count ?? '—'}</td>
                      <td>{col.segments_count ?? '—'}</td>
                      <td>{col.shards_count ?? '—'}</td>
                      <td>{col.replication_factor ?? '—'}</td>
                      <td>
                        {col.vectors_config ? (
                          <div className="vectors-config">
                            <span className="vector-badge">{col.vectors_config.name || 'Default'}</span>
                            <span className="vector-badge">{col.vectors_config.size}</span>
                            <span className="vector-badge">{col.vectors_config.distance || '—'}</span>
                          </div>
                        ) : (
                          '—'
                        )}
                      </td>
                      <td>{col.on_disk ? 'Yes' : 'No'}</td>
                      <td>{col.framework_id || '—'}</td>
                      <td>{col.version || '—'}</td>
                      <td>{col.last_refreshed_at || '—'}</td>
                      <td>{isFramework ? (isLatest ? 'Latest' : 'Archive') : '—'}</td>
                      <td>{isFramework ? ageLabel : '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <p className="rag-trigger-hint" style={{ marginTop: '8px' }}>
              Collections with a framework id come from external framework docs. Rows marked as
              {' '}
              <strong>Latest</strong>
              {' '}
              (e.g. Alamofire_x.m.n_latest) are refreshed automatically when their age exceeds the configured TTL.
            </p>
          </>
        )}
      </div>

      {sheetOpen && (
        <div className="rag-sheet-overlay" onClick={() => setSheetOpen(false)}>
          <div
            className="rag-sheet"
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
          >
            <div className="rag-sheet-header">
              <h3>Keywords that trigger RAG search</h3>
              <button type="button" className="rag-sheet-close" onClick={() => setSheetOpen(false)} aria-label="Close">
                ×
              </button>
            </div>
            <div className="rag-sheet-body">
              <div className="rag-sheet-actions">
                <button
                  type="button"
                  className="rag-button primary"
                  disabled={savingKeywords}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleAddCollection();
                  }}
                >
                  Add collection
                </button>
              </div>
              {keywordCollections.length === 0 ? (
                <div className="empty-state">No keyword collections. Add one to define trigger words.</div>
              ) : (
                <div className="rag-keyword-collections-list">
                  {keywordCollections.map((coll) => {
                    const isEditing = editCollectionId === coll.id;
                    const draft = isEditing ? editDraft : null;
                    return (
                      <div key={coll.id} className="rag-keyword-collection-block">
                        <div className="rag-keyword-collection-header">
                          <label className="rag-keyword-collection-toggle">
                            <input
                              type="checkbox"
                              checked={!!coll.enabled}
                              onChange={() => handleToggleEnabled(coll)}
                            />
                            <span>Enabled</span>
                          </label>
                          {isEditing ? (
                            <input
                              type="text"
                              className="rag-keyword-collection-name-input"
                              value={draft?.name ?? ''}
                              onChange={(e) => setEditDraft((d) => (d ? { ...d, name: e.target.value } : null))}
                              placeholder="Collection name"
                            />
                          ) : (
                            <span className="rag-keyword-collection-name">{coll.name}</span>
                          )}
                          <div className="rag-keyword-collection-buttons">
                            {isEditing ? (
                              <>
                                <button type="button" className="rag-button" onClick={handleSaveEdit} disabled={savingKeywords}>
                                  Save
                                </button>
                                <button type="button" className="rag-button ghost" onClick={handleCancelEdit}>
                                  Cancel
                                </button>
                              </>
                            ) : (
                              <>
                                <button type="button" className="rag-button ghost" onClick={() => handleStartEdit(coll)}>
                                  Edit
                                </button>
                                <button type="button" className="rag-button ghost" onClick={() => handleOpenAddWords(coll)}>
                                  Add
                                </button>
                                <button type="button" className="rag-button ghost" onClick={() => handlePasteIntoCollection(coll)}>
                                  Paste
                                </button>
                                {deleteConfirmId === coll.id ? (
                                  <>
                                    <span className="rag-delete-confirm-text">Delete?</span>
                                    <button type="button" className="rag-button" onClick={() => handleDeleteCollection(coll.id)}>
                                      Yes
                                    </button>
                                    <button type="button" className="rag-button ghost" onClick={() => setDeleteConfirmId(null)}>
                                      No
                                    </button>
                                  </>
                                ) : (
                                  <button type="button" className="rag-button ghost" onClick={() => setDeleteConfirmId(coll.id)}>
                                    Delete
                                  </button>
                                )}
                              </>
                            )}
                          </div>
                        </div>
                        <div className="rag-keyword-collection-keywords">
                          {isEditing && draft ? (
                            <div className="rag-keywords-edit-list">
                              {draft.keywords.map((kw, idx) => (
                                <div key={idx} className="rag-keyword-edit-row">
                                  <input
                                    type="text"
                                    value={kw}
                                    onChange={(e) => {
                                      const next = [...draft.keywords];
                                      next[idx] = e.target.value;
                                      setEditDraft((d) => (d ? { ...d, keywords: next } : null));
                                    }}
                                  />
                                  <button
                                    type="button"
                                    className="rag-button ghost"
                                    onClick={() => {
                                      const next = draft.keywords.filter((_, i) => i !== idx);
                                      setEditDraft((d) => (d ? { ...d, keywords: next } : null));
                                    }}
                                  >
                                    Remove
                                  </button>
                                </div>
                              ))}
                              <button
                                type="button"
                                className="rag-button ghost"
                                onClick={() => setEditDraft((d) => (d ? { ...d, keywords: [...d.keywords, ''] } : null))}
                              >
                                + Add word
                              </button>
                            </div>
                          ) : (
                            <div className="rag-keywords-chips">
                              {(coll.keywords || []).map((kw, idx) => (
                                <span key={idx} className="rag-keyword-chip">
                                  {kw}
                                </span>
                              ))}
                              {(coll.keywords || []).length === 0 && (
                                <span className="rag-keywords-empty">No keywords</span>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
            <div className="rag-sheet-footer">
              <button type="button" className="rag-button" onClick={() => setSheetOpen(false)}>
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {addWordsCollectionId && (
        <div className="rag-sheet-overlay" onClick={() => setAddWordsCollectionId(null)}>
          <div className="rag-sheet rag-add-words-sheet" onClick={(e) => e.stopPropagation()}>
            <div className="rag-sheet-header">
              <h3>Add words</h3>
              <button type="button" className="rag-sheet-close" onClick={() => setAddWordsCollectionId(null)} aria-label="Close">
                ×
              </button>
            </div>
            <div className="rag-sheet-body">
              <p className="rag-add-words-hint">Type a word and press Enter to add. Preview below.</p>
              <input
                type="text"
                className="rag-add-words-input"
                value={addWordsInput}
                onChange={(e) => setAddWordsInput(e.target.value)}
                onKeyDown={handleAddWordInputKeyDown}
                placeholder="Type word and press Enter"
                autoFocus
              />
              <div className="rag-add-words-preview">
                {addWordsList.length === 0 ? '—' : addWordsList.join(', ')}
              </div>
            </div>
            <div className="rag-sheet-footer">
              <button type="button" className="rag-button ghost" onClick={() => setAddWordsCollectionId(null)}>
                Cancel
              </button>
              <button type="button" className="rag-button primary" onClick={handleAddWordsSave} disabled={savingKeywords}>
                Save
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

export default RagTab;
