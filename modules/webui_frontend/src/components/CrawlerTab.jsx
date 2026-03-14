import React, { useEffect, useRef, useState } from 'react';
import { getCrawlerSources, getCrawlerSourcePages, getRagCollections, createCollection, getCreateCollectionStatus, crawlSource, getCrawlStatus, addCrawlerSource, getCrawlerSource, updateCrawlerSource } from '../services/api';
import './CrawlerTab.css';

function CrawlerTab() {
  const [loading, setLoading] = useState(true);
  const [sources, setSources] = useState([]);
  const [selectedSource, setSelectedSource] = useState(null);
  const [sourcePages, setSourcePages] = useState([]);
  const [collections, setCollections] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [createForm, setCreateForm] = useState({
    collection_name: '',
    source_ids: [],
    chunk_max_size: 1200,
    chunk_min_size: 300,
    confidence_threshold: 0.75,
    top_k: 4,
  });
  const [creating, setCreating] = useState(false);
  const [createJobId, setCreateJobId] = useState(null);
  const [createProgress, setCreateProgress] = useState(null);
  const [showCreateToast, setShowCreateToast] = useState(false);
  const [createCollectionName, setCreateCollectionName] = useState('');
  const createToastTimeoutRef = useRef(null);
  const [crawlingSources, setCrawlingSources] = useState(new Set());
  const [showAddSourceModal, setShowAddSourceModal] = useState(false);
  const [addSourceForm, setAddSourceForm] = useState({
    id: '',
    url: '',
    max_depth: 2,
    crawler: 'playwright',
    doc_only: true,
    seed_urls: [],
  });
  const [addingSource, setAddingSource] = useState(false);
  const [showEditSourceModal, setShowEditSourceModal] = useState(false);
  const [editingSourceId, setEditingSourceId] = useState(null);
  const [editSourceForm, setEditSourceForm] = useState({
    id: '',
    url: '',
    max_depth: 2,
    crawler: 'playwright',
    doc_only: true,
    seed_urls: [],
  });
  const [updatingSource, setUpdatingSource] = useState(false);
  const [crawlAllResults, setCrawlAllResults] = useState([]);
  const [selectedSourceIds, setSelectedSourceIds] = useState(new Set());

  const loadSources = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getCrawlerSources();
      const loaded = data.sources || [];
      setSources(loaded);
      // Keep selection only for sources that still exist
      setSelectedSourceIds((prev) => {
        if (!prev || prev.size === 0) return prev;
        const ids = new Set(loaded.map((s) => s.id));
        const next = new Set();
        prev.forEach((id) => {
          if (ids.has(id)) next.add(id);
        });
        return next;
      });
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
      // Non-critical error
      console.warn('Failed to load collections:', e);
    }
  };

  useEffect(() => {
    loadSources();
    loadCollections();
  }, []);

  // Poll create-collection job progress
  useEffect(() => {
    if (!createJobId) return;
    const interval = setInterval(async () => {
      try {
        const job = await getCreateCollectionStatus(createJobId);
        setCreateProgress({
          status: job.status,
          processed_pages: job.processed_pages ?? 0,
          total_pages: job.total_pages ?? 0,
          indexed_pages: job.indexed_pages ?? 0,
          total_chunks: job.total_chunks ?? 0,
          skipped_pages: job.skipped_pages ?? 0,
          error: job.error,
          statistics: job.statistics,
        });
        if (job.status === 'success') {
          setCreateJobId(null);
          setCreating(false);
          setShowCreateModal(false);
          setCreateForm({ collection_name: '', source_ids: [], chunk_max_size: 1200, chunk_min_size: 300, confidence_threshold: 0.75, top_k: 4 });
          setShowCreateToast(true);
          await loadCollections();
          alert(`Collection created successfully! Indexed ${job.indexed_pages ?? 0} pages, ${job.total_chunks ?? 0} chunks.`);
        } else if (job.status === 'failed') {
          setCreateJobId(null);
          setCreating(false);
          setError(job.error || 'Collection creation failed');
        }
      } catch (e) {
        setCreateJobId(null);
        setCreating(false);
        setError(e.message);
      }
    }, 1500);
    return () => clearInterval(interval);
  }, [createJobId]);

  // Auto-hide create-collection toast after completion or failure
  useEffect(() => {
    if (!showCreateToast || !createProgress) {
      return undefined;
    }

    const status = createProgress.status;
    if (status !== 'success' && status !== 'failed') {
      return undefined;
    }

    const timeoutMs = status === 'success' ? 4000 : 7000;

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

  // Poll crawl status for sources that are crawling
  useEffect(() => {
    if (crawlingSources.size === 0) return;

    const interval = setInterval(async () => {
      const statusChecks = Array.from(crawlingSources).map(async (sourceId) => {
        try {
          const status = await getCrawlStatus(sourceId);
          if (status.status === 'finished' || status.status === 'not_running') {
            const returnCode = status.return_code;
            const success = status.status === 'finished' ? (returnCode === 0) : true;
            const errorDetail = (status.stderr && status.stderr.trim()) || null;
            setCrawlAllResults(prev => [...prev, { sourceId, success, returnCode: returnCode ?? undefined, error: errorDetail }]);
            setCrawlingSources(prev => {
              const next = new Set(prev);
              next.delete(sourceId);
              return next;
            });
            loadSources();
            if (selectedSource === sourceId) {
              try {
                const data = await getCrawlerSourcePages(sourceId);
                setSourcePages(data.pages || []);
              } catch (e) {
                console.error(`Failed to reload pages for ${sourceId}:`, e);
              }
            }
          }
        } catch (e) {
          console.error(`Failed to check crawl status for ${sourceId}:`, e);
        }
      });
      await Promise.all(statusChecks);
    }, 2000);

    return () => clearInterval(interval);
  }, [crawlingSources, selectedSource]);

  const handleSourceClick = async (sourceId) => {
    if (selectedSource === sourceId) {
      setSelectedSource(null);
      setSourcePages([]);
      return;
    }
    setSelectedSource(sourceId);
    setError(null);
    try {
      const data = await getCrawlerSourcePages(sourceId);
      setSourcePages(data.pages || []);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleRefresh = () => {
    loadSources();
    loadCollections();
    if (selectedSource) {
      handleSourceClick(selectedSource);
    }
  };

  const formatDate = (dateStr) => {
    if (!dateStr) return 'Never';
    try {
      const date = new Date(dateStr);
      return date.toLocaleString();
    } catch {
      return dateStr;
    }
  };

  const handleCreateCollection = async () => {
    if (!createForm.collection_name.trim()) {
      setError('Collection name is required');
      return;
    }
    if (createForm.source_ids.length === 0) {
      setError('At least one source must be selected');
      return;
    }

    setCreating(true);
    setError(null);
    setCreateProgress(null);
    try {
      const trimmedName = createForm.collection_name.trim();
      setCreateCollectionName(trimmedName);
      setShowCreateToast(true);
      const result = await createCollection(createForm);
      if (result.job_id) {
        setCreateJobId(result.job_id);
        setCreateProgress({ status: 'running', processed_pages: 0, total_pages: 0, indexed_pages: 0, total_chunks: 0 });
      } else {
        setShowCreateModal(false);
        setCreateForm({ collection_name: '', source_ids: [], chunk_max_size: 1200, chunk_min_size: 300, confidence_threshold: 0.75, top_k: 4 });
        await loadCollections();
        alert('Collection created successfully!');
        setCreating(false);
        setShowCreateToast(false);
        setCreateProgress(null);
      }
    } catch (e) {
      setError(e.message);
      setCreating(false);
      setShowCreateToast(false);
    }
  };

  const handleCloseCreateToast = () => {
    setShowCreateToast(false);
    setCreateProgress(null);
  };

  const toggleSourceSelected = (sourceId) => {
    setSelectedSourceIds((prev) => {
      const next = new Set(prev);
      if (next.has(sourceId)) {
        next.delete(sourceId);
      } else {
        next.add(sourceId);
      }
      return next;
    });
  };

  const handleToggleSelectAll = () => {
    setSelectedSourceIds((prev) => {
      if (!sources.length) return new Set();
      const allSelected = sources.every((s) => prev.has(s.id));
      if (allSelected) {
        return new Set();
      }
      return new Set(sources.map((s) => s.id));
    });
  };

  const toggleSourceInForm = (sourceId) => {
    setCreateForm(prev => ({
      ...prev,
      source_ids: prev.source_ids.includes(sourceId)
        ? prev.source_ids.filter(id => id !== sourceId)
        : [...prev.source_ids, sourceId],
    }));
  };

  const handleCrawlSource = async (sourceId) => {
    if (crawlingSources.has(sourceId)) return;
    setCrawlAllResults([]);
    setCrawlingSources(prev => new Set(prev).add(sourceId));
    setError(null);
    try {
      await crawlSource(sourceId);
    } catch (e) {
      setError(e.message);
      setCrawlAllResults(prev => [...prev, { sourceId, success: false, returnCode: undefined, error: e.message }]);
      setCrawlingSources(prev => {
        const next = new Set(prev);
        next.delete(sourceId);
        return next;
      });
    }
  };

  const handleCrawlAll = async () => {
    if (sources.length === 0 || crawlingSources.size > 0) return;
    setCrawlAllResults([]);
    setError(null);
    const ids = sources.map(s => s.id);
    setCrawlingSources(prev => new Set([...prev, ...ids]));
    for (const sourceId of ids) {
      try {
        await crawlSource(sourceId);
      } catch (e) {
        setError(e.message);
        setCrawlAllResults(prev => [...prev, { sourceId, success: false, returnCode: undefined, error: e.message }]);
        setCrawlingSources(prev => {
          const next = new Set(prev);
          next.delete(sourceId);
          return next;
        });
      }
    }
  };

  const handleCrawlSelected = () => {
    if (busy || crawlingSources.size > 0 || selectedSourceIds.size === 0) return;
    const ids = sources.filter((s) => selectedSourceIds.has(s.id)).map((s) => s.id);
    if (!ids.length) return;
    ids.forEach((id) => {
      handleCrawlSource(id);
    });
  };

  const handleAddSource = async () => {
    if (!addSourceForm.id.trim() || !addSourceForm.url.trim()) {
      setError('Source ID and URL are required');
      return;
    }
    
    // Filter out empty seed URLs
    const seedUrls = addSourceForm.seed_urls.filter(url => url && url.trim());
    
    setAddingSource(true);
    setError(null);
    try {
      await addCrawlerSource({
        ...addSourceForm,
        seed_urls: seedUrls,
      });
      setShowAddSourceModal(false);
      setAddSourceForm({
        id: '',
        url: '',
        max_depth: 2,
        crawler: 'playwright',
        doc_only: true,
        seed_urls: [],
      });
      await loadSources();
      alert('Source added successfully!');
    } catch (e) {
      setError(e.message);
    } finally {
      setAddingSource(false);
    }
  };

  const handleEditSource = async (sourceId) => {
    setEditingSourceId(sourceId);
    setError(null);
    try {
      const sourceData = await getCrawlerSource(sourceId);
      setEditSourceForm({
        id: sourceData.id,
        url: sourceData.url || '',
        max_depth: sourceData.max_depth || 2,
        crawler: sourceData.crawler || 'playwright',
        doc_only: sourceData.doc_only !== undefined ? sourceData.doc_only : true,
        seed_urls: sourceData.seed_urls || [],
      });
      setShowEditSourceModal(true);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleUpdateSource = async () => {
    if (!editSourceForm.url.trim()) {
      setError('URL is required');
      return;
    }
    
    // Filter out empty seed URLs
    const seedUrls = editSourceForm.seed_urls.filter(url => url && url.trim());
    
    setUpdatingSource(true);
    setError(null);
    try {
      await updateCrawlerSource(editingSourceId, {
        url: editSourceForm.url,
        max_depth: editSourceForm.max_depth,
        crawler: editSourceForm.crawler,
        doc_only: editSourceForm.doc_only,
        seed_urls: seedUrls,
      });
      setShowEditSourceModal(false);
      setEditingSourceId(null);
      await loadSources();
      alert('Source updated successfully!');
    } catch (e) {
      setError(e.message);
    } finally {
      setUpdatingSource(false);
    }
  };

  return (
    <div className="crawler-tab">
      <div className="crawler-header">
        <h2>Crawler / Indexer</h2>
        <div className="crawler-actions">
          <button
            type="button"
            className="crawler-button primary"
            onClick={() => handleCrawlSource(selectedSource)}
            disabled={busy || !selectedSource || crawlingSources.has(selectedSource)}
            title={!selectedSource ? 'Select a source to crawl' : ''}
          >
            Crawl
          </button>
          <button
            type="button"
            className="crawler-button primary"
            onClick={handleCrawlAll}
            disabled={busy || sources.length === 0 || crawlingSources.size > 0}
            title="Crawl all configured sources"
          >
            Crawl ALL
          </button>
          <button
            type="button"
            className="crawler-button primary"
            onClick={handleCrawlSelected}
            disabled={busy || selectedSourceIds.size === 0 || crawlingSources.size > 0}
            title="Crawl selected sources"
          >
            Crawl selected
          </button>
          <button
            type="button"
            className="crawler-button primary"
            onClick={() => setShowAddSourceModal(true)}
          >
            Add Source
          </button>
          <button
            type="button"
            className="crawler-button primary"
            onClick={() => setShowCreateModal(true)}
            disabled={busy || sources.length === 0}
          >
            Create Collection
          </button>
          <button
            type="button"
            className="crawler-button ghost"
            onClick={handleRefresh}
            disabled={busy}
          >
            Refresh
          </button>
        </div>
      </div>

      {crawlingSources.size > 0 && (
        <div className="crawler-progress-panel crawler-progress-panel-fixed" role="status" aria-live="polite">
          <div className="crawler-progress-header">
            <span className="crawler-progress-spinner" aria-hidden="true" />
            <span className="crawler-progress-title">Crawling…</span>
            <span className="crawler-progress-sources">
              {Array.from(crawlingSources).join(', ')}
            </span>
          </div>
        </div>
      )}

      {createProgress && showCreateToast && (
        <div
          className={`create-collection-toast create-collection-toast-${createProgress.status || 'unknown'}`}
          role="status"
          aria-live="polite"
        >
          <div className="create-collection-toast-header">
            <div className="create-collection-toast-title">
              {createProgress.status === 'success'
                ? 'Collection created'
                : createProgress.status === 'failed'
                  ? 'Collection failed'
                  : 'Creating collection…'}
            </div>
            <button
              type="button"
              className="create-collection-toast-close"
              onClick={handleCloseCreateToast}
              aria-label="Dismiss collection progress"
            >
              ×
            </button>
          </div>
          <div className="create-collection-toast-body">
            <div className="create-collection-toast-name">
              {createCollectionName || createForm.collection_name || 'Collection'}
            </div>
            {createProgress.status === 'running' && (
              <div className="create-collection-toast-running">
                <span className="create-collection-toast-spinner" aria-hidden="true" />
                <span className="create-collection-toast-text">
                  Indexed {createProgress.indexed_pages} / {createProgress.total_pages || '…'} pages ({createProgress.total_chunks} chunks)
                </span>
              </div>
            )}
            {(createProgress.status === 'success' || createProgress.status === 'failed') && (
              <div className="create-collection-toast-text">
                {createProgress.status === 'success'
                  ? `Indexed ${createProgress.indexed_pages ?? 0} pages, ${createProgress.total_chunks ?? 0} chunks.`
                  : (createProgress.error && String(createProgress.error).slice(0, 240)) || 'Collection creation failed.'}
              </div>
            )}
            {createProgress.total_pages > 0 && createProgress.status === 'running' && (
              <div className="create-collection-toast-progress-bar-wrap">
                <div
                  className="create-collection-toast-progress-bar-fill"
                  style={{
                    width: `${Math.round(
                      (100 * createProgress.processed_pages) / (createProgress.total_pages || 1),
                    )}%`,
                  }}
                />
              </div>
            )}
          </div>
        </div>
      )}

      {crawlAllResults.length > 0 && crawlingSources.size === 0 && (
        <div className="modal-overlay" onClick={() => setCrawlAllResults([])}>
          <div className="modal-content crawler-result-modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>
                {crawlAllResults.length === 1 ? 'Crawl finished' : 'Crawl ALL finished'}
              </h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setCrawlAllResults([])}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              {crawlAllResults.length === 1 ? (
                (() => {
                  const r = crawlAllResults[0];
                  return (
                    <p>
                      <strong>{r.sourceId}</strong>: {r.success
                        ? 'Completed successfully.'
                        : r.error || `Failed (return code ${r.returnCode ?? '—'}).`}
                    </p>
                  );
                })()
              ) : (
                <>
                  <p className="crawler-result-summary">
                    Succeeded: {crawlAllResults.filter(r => r.success).length}, Failed: {crawlAllResults.filter(r => !r.success).length}
                  </p>
                  <ul className="crawler-result-list">
                    {crawlAllResults.map((r, i) => (
                      <li key={i}>
                        <strong>{r.sourceId}</strong>: {r.success ? 'OK' : (r.error || `code ${r.returnCode ?? '—'}`)}
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </div>
            <div className="modal-footer">
              <button type="button" className="crawler-button primary" onClick={() => setCrawlAllResults([])}>
                OK
              </button>
            </div>
          </div>
        </div>
      )}

      {error && <div className="crawler-error">Error: {error}</div>}

      {loading ? (
        <div className="loading">Loading sources...</div>
      ) : !sources.length ? (
        <div className="empty-state">No crawl sources found. Run crawler first.</div>
      ) : (
        <div className="crawler-sources">
          <div className="sources-header">
            <h3>Crawl Sources</h3>
          </div>
          <table className="sources-table">
            <thead>
              <tr>
                <th className="select-cell">
                  <input
                    type="checkbox"
                    aria-label="Select all sources"
                    checked={sources.length > 0 && sources.every((s) => selectedSourceIds.has(s.id))}
                    onChange={handleToggleSelectAll}
                  />
                </th>
                <th>Source ID</th>
                <th>URL</th>
                <th>Last Crawled</th>
                <th>Total Pages</th>
                <th>Indexed</th>
                <th>Dirty</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((source) => (
                <React.Fragment key={source.id}>
                  <tr>
                    <td className="select-cell">
                      <input
                        type="checkbox"
                        aria-label={`Select source ${source.id}`}
                        checked={selectedSourceIds.has(source.id)}
                        onChange={() => toggleSourceSelected(source.id)}
                      />
                    </td>
                    <td>{source.id}</td>
                    <td className="url-cell">{source.url || '—'}</td>
                    <td>{formatDate(source.last_crawled)}</td>
                    <td>{source.total_pages || 0}</td>
                    <td>
                      <span className={`status-badge ${source.indexed_pages > 0 ? 'indexed' : 'not-indexed'}`}>
                        {source.indexed_pages || 0}
                      </span>
                    </td>
                    <td>
                      <span className={`status-badge ${source.dirty_pages > 0 ? 'dirty' : 'clean'}`}>
                        {source.dirty_pages || 0}
                      </span>
                    </td>
                    <td>
                      <div className="source-actions">
                        <button
                          type="button"
                          className="crawler-button small"
                          onClick={() => handleSourceClick(source.id)}
                        >
                          {selectedSource === source.id ? 'Hide' : 'View'} Details
                        </button>
                        <button
                          type="button"
                          className="crawler-button small"
                          onClick={() => handleEditSource(source.id)}
                          title="Edit source configuration"
                        >
                          ✏️ Edit
                        </button>
                        <button
                          type="button"
                          className="crawler-button small refresh"
                          onClick={() => handleCrawlSource(source.id)}
                          disabled={crawlingSources.has(source.id)}
                          title="Refresh/Crawl this source"
                        >
                          {crawlingSources.has(source.id) ? (
                            <>
                              <span className="spinner"></span> Crawling...
                            </>
                          ) : (
                            '🔄 Refresh'
                          )}
                        </button>
                      </div>
                    </td>
                  </tr>
                  {selectedSource === source.id && (
                    <tr>
                      <td colSpan="7" className="details-cell">
                        <div className="source-details">
                          <h4>Source Details</h4>
                          <div className="details-grid">
                            <div className="detail-item">
                              <span className="detail-label">Source ID:</span>
                              <span className="detail-value">{source.id}</span>
                            </div>
                            {source.max_depth && (
                              <div className="detail-item">
                                <span className="detail-label">Max Depth:</span>
                                <span className="detail-value">{source.max_depth}</span>
                              </div>
                            )}
                            {source.crawler && (
                              <div className="detail-item">
                                <span className="detail-label">Crawler:</span>
                                <span className="detail-value">{source.crawler}</span>
                              </div>
                            )}
                            {source.seed_urls && source.seed_urls.length > 0 && (
                              <div className="detail-item full-width">
                                <span className="detail-label">Seed URLs:</span>
                                <ul className="seed-urls-list">
                                  {source.seed_urls.slice(0, 10).map((url, idx) => (
                                    <li key={idx}>{url}</li>
                                  ))}
                                  {source.seed_urls.length > 10 && (
                                    <li className="more-urls">... and {source.seed_urls.length - 10} more</li>
                                  )}
                                </ul>
                              </div>
                            )}
                          </div>
                          {sourcePages.length > 0 && (
                            <div className="pages-section">
                              <h5>Recent Pages ({sourcePages.length} total)</h5>
                              <div className="pages-list">
                                {sourcePages.slice(0, 20).map((page, idx) => (
                                  <div key={idx} className="page-item">
                                    <span className="page-filename">{page.filename}</span>
                                    <span className="page-url">{page.url}</span>
                                    <span className={`page-status ${page.dirty ? 'dirty' : 'clean'}`}>
                                      {page.dirty ? 'Dirty' : 'Clean'}
                                    </span>
                                    {page.has_chunks && (
                                      <span className="page-chunks">{page.chunk_count} chunks</span>
                                    )}
                                  </div>
                                ))}
                                {sourcePages.length > 20 && (
                                  <div className="more-pages">... and {sourcePages.length - 20} more pages</div>
                                )}
                              </div>
                            </div>
                          )}
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Create New Collection</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowCreateModal(false)}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              {createProgress && (
                <div className="create-collection-progress">
                  <div className="progress-text">
                    {createProgress.status === 'running'
                      ? `Indexed ${createProgress.indexed_pages} / ${createProgress.total_pages || '…'} pages (${createProgress.total_chunks} chunks)`
                      : createProgress.status === 'success'
                        ? `Done: ${createProgress.indexed_pages} pages, ${createProgress.total_chunks} chunks`
                        : null}
                  </div>
                  {createProgress.total_pages > 0 && createProgress.status === 'running' && (
                    <div className="progress-bar-wrap">
                      <div
                        className="progress-bar-fill"
                        style={{ width: `${Math.round((100 * createProgress.processed_pages) / createProgress.total_pages)}%` }}
                      />
                    </div>
                  )}
                </div>
              )}
              <div className="form-group">
                <label>Collection Name *</label>
                <input
                  type="text"
                  value={createForm.collection_name}
                  onChange={(e) => setCreateForm(prev => ({ ...prev, collection_name: e.target.value }))}
                  placeholder="my_collection"
                />
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
                      <span>{source.id} ({source.total_pages || 0} pages)</span>
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
                    onChange={(e) => setCreateForm(prev => ({ ...prev, chunk_max_size: parseInt(e.target.value) || 1200 }))}
                    min="100"
                    max="5000"
                  />
                </div>
                <div className="form-group">
                  <label>Chunk Min Size</label>
                  <input
                    type="number"
                    value={createForm.chunk_min_size}
                    onChange={(e) => setCreateForm(prev => ({ ...prev, chunk_min_size: parseInt(e.target.value) || 300 }))}
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
                    onChange={(e) => setCreateForm(prev => ({ ...prev, confidence_threshold: parseFloat(e.target.value) || 0.75 }))}
                    min="0"
                    max="1"
                  />
                </div>
                <div className="form-group">
                  <label>Top K</label>
                  <input
                    type="number"
                    value={createForm.top_k}
                    onChange={(e) => setCreateForm(prev => ({ ...prev, top_k: parseInt(e.target.value) || 4 }))}
                    min="1"
                    max="20"
                  />
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="crawler-button"
                onClick={() => setShowCreateModal(false)}
                disabled={creating}
              >
                Cancel
              </button>
              <button
                type="button"
                className="crawler-button primary"
                onClick={handleCreateCollection}
                disabled={creating}
              >
                {creating ? 'Creating...' : 'Create Collection'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showAddSourceModal && (
        <div className="modal-overlay" onClick={() => setShowAddSourceModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Add New Source</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowAddSourceModal(false)}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Source ID *</label>
                <input
                  type="text"
                  value={addSourceForm.id}
                  onChange={(e) => setAddSourceForm(prev => ({ ...prev, id: e.target.value }))}
                  placeholder="my_source"
                />
                <div className="form-hint">Alphanumeric, underscores, and hyphens only</div>
              </div>
              <div className="form-group">
                <label>URL *</label>
                <input
                  type="url"
                  value={addSourceForm.url}
                  onChange={(e) => setAddSourceForm(prev => ({ ...prev, url: e.target.value }))}
                  placeholder="https://example.com/documentation"
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Max Depth</label>
                  <input
                    type="number"
                    value={addSourceForm.max_depth}
                    onChange={(e) => setAddSourceForm(prev => ({ ...prev, max_depth: parseInt(e.target.value) || 2 }))}
                    min="1"
                    max="5"
                  />
                </div>
                <div className="form-group">
                  <label>Crawler</label>
                  <select
                    value={addSourceForm.crawler}
                    onChange={(e) => setAddSourceForm(prev => ({ ...prev, crawler: e.target.value }))}
                  >
                    <option value="playwright">Playwright</option>
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={addSourceForm.doc_only}
                    onChange={(e) => setAddSourceForm(prev => ({ ...prev, doc_only: e.target.checked }))}
                  />
                  Doc Only (restrict to documentation pages)
                </label>
              </div>
              <div className="form-group">
                <label>Seed URLs (optional)</label>
                <div className="seed-urls-editor">
                  <div className="seed-urls-list-editor">
                    {addSourceForm.seed_urls.map((url, index) => (
                      <div key={index} className="seed-url-item">
                        <input
                          type="url"
                          value={url}
                          onChange={(e) => {
                            const newUrls = [...addSourceForm.seed_urls];
                            newUrls[index] = e.target.value;
                            setAddSourceForm(prev => ({ ...prev, seed_urls: newUrls }));
                          }}
                          placeholder="https://example.com/page"
                          className="seed-url-input"
                        />
                        <button
                          type="button"
                          className="crawler-button small remove"
                          onClick={() => {
                            const newUrls = addSourceForm.seed_urls.filter((_, i) => i !== index);
                            setAddSourceForm(prev => ({ ...prev, seed_urls: newUrls }));
                          }}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="crawler-button small"
                    onClick={() => {
                      setAddSourceForm(prev => ({
                        ...prev,
                        seed_urls: [...prev.seed_urls, ''],
                      }));
                    }}
                  >
                    + Add Seed URL
                  </button>
                  <div className="form-hint">
                    Additional entry points for the crawler. Each URL should be on a new line or separate entry.
                  </div>
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="crawler-button"
                onClick={() => setShowAddSourceModal(false)}
                disabled={addingSource}
              >
                Cancel
              </button>
              <button
                type="button"
                className="crawler-button primary"
                onClick={handleAddSource}
                disabled={addingSource}
              >
                {addingSource ? 'Adding...' : 'Add Source'}
              </button>
            </div>
          </div>
        </div>
      )}

      {showEditSourceModal && (
        <div className="modal-overlay" onClick={() => setShowEditSourceModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h3>Edit Source: {editingSourceId}</h3>
              <button
                type="button"
                className="modal-close"
                onClick={() => setShowEditSourceModal(false)}
              >
                ×
              </button>
            </div>
            <div className="modal-body">
              <div className="form-group">
                <label>Source ID</label>
                <input
                  type="text"
                  value={editSourceForm.id}
                  disabled
                  style={{ opacity: 0.6, cursor: 'not-allowed' }}
                />
                <div className="form-hint">Source ID cannot be changed</div>
              </div>
              <div className="form-group">
                <label>URL *</label>
                <input
                  type="url"
                  value={editSourceForm.url}
                  onChange={(e) => setEditSourceForm(prev => ({ ...prev, url: e.target.value }))}
                  placeholder="https://example.com/documentation"
                />
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Max Depth</label>
                  <input
                    type="number"
                    value={editSourceForm.max_depth}
                    onChange={(e) => setEditSourceForm(prev => ({ ...prev, max_depth: parseInt(e.target.value) || 2 }))}
                    min="1"
                    max="5"
                  />
                </div>
                <div className="form-group">
                  <label>Crawler</label>
                  <select
                    value={editSourceForm.crawler}
                    onChange={(e) => setEditSourceForm(prev => ({ ...prev, crawler: e.target.value }))}
                  >
                    <option value="playwright">Playwright</option>
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label>
                  <input
                    type="checkbox"
                    checked={editSourceForm.doc_only}
                    onChange={(e) => setEditSourceForm(prev => ({ ...prev, doc_only: e.target.checked }))}
                  />
                  Doc Only (restrict to documentation pages)
                </label>
              </div>
              <div className="form-group">
                <label>Seed URLs (optional)</label>
                <div className="seed-urls-editor">
                  <div className="seed-urls-list-editor">
                    {editSourceForm.seed_urls.map((url, index) => (
                      <div key={index} className="seed-url-item">
                        <input
                          type="url"
                          value={url}
                          onChange={(e) => {
                            const newUrls = [...editSourceForm.seed_urls];
                            newUrls[index] = e.target.value;
                            setEditSourceForm(prev => ({ ...prev, seed_urls: newUrls }));
                          }}
                          placeholder="https://example.com/page"
                          className="seed-url-input"
                        />
                        <button
                          type="button"
                          className="crawler-button small remove"
                          onClick={() => {
                            const newUrls = editSourceForm.seed_urls.filter((_, i) => i !== index);
                            setEditSourceForm(prev => ({ ...prev, seed_urls: newUrls }));
                          }}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                  <button
                    type="button"
                    className="crawler-button small"
                    onClick={() => {
                      setEditSourceForm(prev => ({
                        ...prev,
                        seed_urls: [...prev.seed_urls, ''],
                      }));
                    }}
                  >
                    + Add Seed URL
                  </button>
                  <div className="form-hint">
                    Additional entry points for the crawler. Each URL should be on a new line or separate entry.
                  </div>
                </div>
              </div>
            </div>
            <div className="modal-footer">
              <button
                type="button"
                className="crawler-button"
                onClick={() => setShowEditSourceModal(false)}
                disabled={updatingSource}
              >
                Cancel
              </button>
              <button
                type="button"
                className="crawler-button primary"
                onClick={handleUpdateSource}
                disabled={updatingSource}
              >
                {updatingSource ? 'Updating...' : 'Update Source'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default CrawlerTab;

