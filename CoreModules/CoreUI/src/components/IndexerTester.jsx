import { useEffect, useRef, useState } from 'react';
import {
  getIndexerTesterSources,
  getIndexerTesterFiles,
  getIndexerTesterFileDetail,
  evaluateIndexerWithLlm,
  startIndexerTesterEvaluateBatch,
  getIndexerTesterEvaluateBatchStatus,
  detectBatchEvalPatterns,
  getProviderCatalog,
} from '../services/api';
import { isLogicalRagModelId } from '../constants/llmProxyModels';
import '../styles/components/IndexerTester.css';

function computeIndexerDiff(sourceText, processedText) {
  if (!sourceText && !processedText) return [];
  const sourceLines = (sourceText || '').split('\n');
  const processedLines = (processedText || '').split('\n');
  const maxLen = Math.max(sourceLines.length, processedLines.length);
  const lines = [];
  for (let i = 0; i < maxLen; i += 1) {
    const src = sourceLines[i] ?? '';
    const dst = processedLines[i] ?? '';
    const dstIsFence = dst.trim().startsWith('```');
    if (src === dst) {
      lines.push({
        key: i,
        type: 'same',
        text: src,
      });
    } else if (dst && dstIsFence && src !== dst) {
      lines.push({
        key: i,
        type: 'fence_added',
        text: `+ ${dst}`,
      });
    } else if (src) {
      lines.push({
        key: i,
        type: 'removed',
        text: `- ${src}`,
      });
    } else if (dst) {
      // Generic added line (non-fence) — keep but mark as same to avoid noise.
      lines.push({
        key: i,
        type: 'same',
        text: dst,
      });
    }
  }
  return lines;
}

const EVAL_LIMITS_STORAGE_KEY = 'crawler_indexer_eval_limits';
function defaultEvalLimits() {
  return { original_max_chars: 40000, processed_max_chars: 40000, removed_max_chars: 24000 };
}

function IndexerTester() {
  const [testerSources, setTesterSources] = useState([]);
  const [testerLoading, setTesterLoading] = useState(false);
  const [testerError, setTesterError] = useState(null);
  const [testerSelectedSourceId, setTesterSelectedSourceId] = useState('');
  const [testerFiles, setTesterFiles] = useState([]);
  const [testerFilesLoading, setTesterFilesLoading] = useState(false);
  const [testerSortBy, setTesterSortBy] = useState('name');
  const [testerSortOrder, setTesterSortOrder] = useState('asc');
  const [testerSelectedFile, setTesterSelectedFile] = useState(null);
  const [testerFileDetail, setTesterFileDetail] = useState(null);
  const [testerDetailLoading, setTesterDetailLoading] = useState(false);
  const [showIndexerDetailModal, setShowIndexerDetailModal] = useState(false);
  const [indexerSectionOpen, setIndexerSectionOpen] = useState({
    original: false,
    diff: true,
    processed: true,
    llm: false,
  });
  const [llmCatalog, setLlmCatalog] = useState({ providers: [], models: [] });
  const [llmSelectedProviderId, setLlmSelectedProviderId] = useState('');
  const [llmSelectedModel, setLlmSelectedModel] = useState('');
  const [llmEvaluateReply, setLlmEvaluateReply] = useState(null);
  const [llmEvaluateError, setLlmEvaluateError] = useState(null);
  const [llmEvaluateLoading, setLlmEvaluateLoading] = useState(false);
  const [showBatchEvalModal, setShowBatchEvalModal] = useState(false);
  const [batchEvalSourceId, setBatchEvalSourceId] = useState('');
  const [batchEvalModel, setBatchEvalModel] = useState('');
  const [batchEvalCount, setBatchEvalCount] = useState(5);
  const [batchEvalJobId, setBatchEvalJobId] = useState(null);
  const [batchEvalStatus, setBatchEvalStatus] = useState(null);
  const [batchEvalCatalog, setBatchEvalCatalog] = useState({ providers: [], models: [] });
  const [batchEvalProviderId, setBatchEvalProviderId] = useState('');
  const [batchEvalPatterns, setBatchEvalPatterns] = useState(null);
  const [batchEvalPatternsLoading, setBatchEvalPatternsLoading] = useState(false);
  const [batchEvalViewProcessed, setBatchEvalViewProcessed] = useState(null);
  const batchEvalPollingRef = useRef(null);
  const llmModels = (llmCatalog.models || []).filter(
    (m) => !llmSelectedProviderId || m.provider_id === llmSelectedProviderId,
  );
  const batchEvalModels = (batchEvalCatalog.models || []).filter(
    (m) => !batchEvalProviderId || m.provider_id === batchEvalProviderId,
  );

  const [evalLimits, setEvalLimits] = useState(() => {
    try {
      const raw = localStorage.getItem(EVAL_LIMITS_STORAGE_KEY);
      if (!raw) return defaultEvalLimits();
      const parsed = JSON.parse(raw);
      const o = defaultEvalLimits();
      if (typeof parsed.original_max_chars === 'number' && parsed.original_max_chars >= 1000) o.original_max_chars = parsed.original_max_chars;
      if (typeof parsed.processed_max_chars === 'number' && parsed.processed_max_chars >= 1000) o.processed_max_chars = parsed.processed_max_chars;
      if (typeof parsed.removed_max_chars === 'number' && parsed.removed_max_chars >= 1000) o.removed_max_chars = parsed.removed_max_chars;
      return o;
    } catch {
      return defaultEvalLimits();
    }
  });
  const setEvalLimitsAndSave = (next) => {
    setEvalLimits((prev) => {
      const out = typeof next === 'function' ? next(prev) : next;
      try {
        localStorage.setItem(EVAL_LIMITS_STORAGE_KEY, JSON.stringify(out));
      } catch {
        // safe: localStorage may be unavailable
      }
      return out;
    });
  };

  const loadIndexerTesterSources = async () => {
    setTesterLoading(true);
    setTesterError(null);
    try {
      const data = await getIndexerTesterSources();
      const list = data.sources || [];
      setTesterSources(list);
      setTesterSelectedSourceId((prev) => {
        if (prev && list.some((s) => s.id === prev)) return prev;
        return list.length > 0 ? list[0].id : '';
      });
    } catch (e) {
      setTesterError(e.message);
      setTesterSources([]);
      setTesterSelectedSourceId('');
    } finally {
      setTesterLoading(false);
    }
  };

  const loadIndexerTesterFiles = async (sourceId, opts = {}) => {
    if (!sourceId) {
      setTesterFiles([]);
      return;
    }
    setTesterFilesLoading(true);
    setTesterError(null);
    try {
      const data = await getIndexerTesterFiles(sourceId, {
        sortBy: opts.sortBy || testerSortBy,
        order: opts.order || testerSortOrder,
      });
      setTesterFiles(data.files || []);
    } catch (e) {
      setTesterError(e.message);
      setTesterFiles([]);
    } finally {
      setTesterFilesLoading(false);
    }
  };

  useEffect(() => {
    if (!testerSources.length) {
      loadIndexerTesterSources();
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (testerSelectedSourceId) {
      loadIndexerTesterFiles(testerSelectedSourceId);
    } else {
      setTesterFiles([]);
    }
    setTesterSelectedFile(null);
    setTesterFileDetail(null);
  }, [testerSelectedSourceId, testerSortBy, testerSortOrder]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleTesterSort = (field) => {
    setTesterSortBy((prevField) => {
      if (prevField === field) {
        setTesterSortOrder((prevOrder) => (prevOrder === 'asc' ? 'desc' : 'asc'));
        return prevField;
      }
      setTesterSortOrder('asc');
      return field;
    });
  };

  const handleTesterSelectFile = async (file) => {
    if (!file) {
      setTesterSelectedFile(null);
      setTesterFileDetail(null);
      setShowIndexerDetailModal(false);
      return;
    }
    setTesterSelectedFile(file.filename);
    setShowIndexerDetailModal(true);
    setTesterDetailLoading(true);
    setTesterError(null);
    try {
      const detail = await getIndexerTesterFileDetail(testerSelectedSourceId, file.filename);
      setTesterFileDetail(detail);
      setIndexerSectionOpen({ original: false, diff: true, processed: true, llm: false });
      setLlmEvaluateReply(null);
      setLlmEvaluateError(null);
    } catch (e) {
      setTesterError(e.message);
      setTesterFileDetail(null);
    } finally {
      setTesterDetailLoading(false);
    }
  };

  const handleCloseIndexerDetailModal = () => setShowIndexerDetailModal(false);
  const toggleIndexerSection = (section) => {
    setIndexerSectionOpen((prev) => ({ ...prev, [section]: !prev[section] }));
  };

  useEffect(() => {
    if (!indexerSectionOpen.llm || !showIndexerDetailModal || (llmCatalog.models || []).length > 0) return;
    getProviderCatalog('chat')
      .then((catalog) => {
        const providers = catalog?.providers || [];
        const models = catalog?.models || [];
        setLlmCatalog({ providers, models });
        if (models.length > 0 && !llmSelectedModel) {
          const preferred =
            models.find((m) => m.id && !isLogicalRagModelId(m.id)) || models[0];
          setLlmSelectedProviderId(preferred.provider_id || '');
          setLlmSelectedModel(preferred.id || preferred.name || '');
        }
      })
      .catch(() => setLlmCatalog({ providers: [], models: [] }));
  }, [indexerSectionOpen.llm, showIndexerDetailModal, llmCatalog.models, llmSelectedModel]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleAskLlm = async () => {
    if (!testerFileDetail) return;
    setLlmEvaluateLoading(true);
    setLlmEvaluateError(null);
    setLlmEvaluateReply(null);
    try {
      const data = await evaluateIndexerWithLlm(
        testerFileDetail.source_md,
        testerFileDetail.processed_md,
        llmSelectedProviderId || undefined,
        llmSelectedModel || undefined,
        testerFileDetail.page_meta ?? undefined,
        evalLimits,
      );
      setLlmEvaluateReply(data.reply ?? '');
    } catch (e) {
      setLlmEvaluateError(e.message);
    } finally {
      setLlmEvaluateLoading(false);
    }
  };

  const handleStartBatchEval = async () => {
    const sourceId = batchEvalSourceId || testerSelectedSourceId;
    if (!sourceId) return;
    const count = Math.max(1, Math.min(500, Number(batchEvalCount) || 5));
    setBatchEvalStatus(null);
    setBatchEvalJobId(null);
    setBatchEvalPatterns(null);
    try {
      const data = await startIndexerTesterEvaluateBatch({
        sourceId,
        providerId: batchEvalProviderId || undefined,
        model: batchEvalModel || undefined,
        count,
        original_max_chars: evalLimits.original_max_chars,
        processed_max_chars: evalLimits.processed_max_chars,
        removed_max_chars: evalLimits.removed_max_chars,
      });
      setBatchEvalJobId(data.job_id);
      setBatchEvalStatus({ status: 'running', total: 0, done: 0, current_file: null, results: [], error: null, source_id: sourceId });
    } catch (e) {
      setBatchEvalStatus({ status: 'error', total: 0, done: 0, current_file: null, results: [], error: e.message });
    }
  };

  useEffect(() => {
    if (!batchEvalJobId || !showBatchEvalModal) return;
    const poll = async () => {
      try {
        const job = await getIndexerTesterEvaluateBatchStatus(batchEvalJobId);
        setBatchEvalStatus((prev) => ({
          status: job.status,
          total: job.total ?? 0,
          done: job.done ?? 0,
          current_file: job.current_file ?? null,
          results: job.results ?? [],
          error: job.error ?? null,
          source_id: job.source_id ?? prev?.source_id ?? null,
        }));
        if (job.status === 'done' || job.status === 'error') {
          if (batchEvalPollingRef.current) {
            clearInterval(batchEvalPollingRef.current);
            batchEvalPollingRef.current = null;
          }
        }
      } catch {
        // keep polling on network error
      }
    };
    poll();
    batchEvalPollingRef.current = setInterval(poll, 1500);
    return () => {
      if (batchEvalPollingRef.current) {
        clearInterval(batchEvalPollingRef.current);
        batchEvalPollingRef.current = null;
      }
    };
  }, [batchEvalJobId, showBatchEvalModal]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleCloseBatchEvalModal = () => {
    if (batchEvalPollingRef.current) {
      clearInterval(batchEvalPollingRef.current);
      batchEvalPollingRef.current = null;
    }
    setShowBatchEvalModal(false);
    setBatchEvalJobId(null);
    setBatchEvalStatus(null);
    setBatchEvalPatterns(null);
    setBatchEvalViewProcessed(null);
  };

  const handleDetectBatchPatterns = async () => {
    const results = batchEvalStatus?.results || [];
    if (!results.length) return;
    setBatchEvalPatternsLoading(true);
    setBatchEvalPatterns(null);
    try {
      const data = await detectBatchEvalPatterns(
        results,
        batchEvalProviderId || undefined,
        batchEvalModel || undefined,
      );
      setBatchEvalPatterns(data.patterns ?? '');
    } catch (e) {
      setBatchEvalPatterns(`Error: ${e.message}`);
    } finally {
      setBatchEvalPatternsLoading(false);
    }
  };

  const handleViewProcessed = async (filename) => {
    const sourceId = batchEvalStatus?.source_id || batchEvalSourceId || testerSelectedSourceId;
    if (!sourceId) return;
    setBatchEvalViewProcessed({ filename, loading: true });
    try {
      const data = await getIndexerTesterFileDetail(sourceId, filename);
      setBatchEvalViewProcessed({
        filename,
        processed_md: data.processed_md ?? '',
        loading: false,
      });
    } catch (e) {
      setBatchEvalViewProcessed({ filename, error: e.message, loading: false });
    }
  };

  const handleDownloadProcessedMd = () => {
    if (batchEvalViewProcessed?.processed_md == null) return;
    const blob = new Blob([batchEvalViewProcessed.processed_md], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = batchEvalViewProcessed.filename || 'processed.md';
    a.click();
    URL.revokeObjectURL(url);
  };

  const openBatchEvalModal = () => {
    setBatchEvalSourceId(testerSelectedSourceId || (testerSources[0]?.id ?? ''));
    setBatchEvalJobId(null);
    setBatchEvalStatus(null);
    setShowBatchEvalModal(true);
    getProviderCatalog('chat')
      .then((catalog) => {
        const providers = catalog?.providers || [];
        const models = catalog?.models || [];
        setBatchEvalCatalog({ providers, models });
        const preferred =
          models.find((m) => m.id && !isLogicalRagModelId(m.id)) || models[0] || null;
        setBatchEvalProviderId(preferred?.provider_id || '');
        setBatchEvalModel(preferred?.id || preferred?.name || '');
      })
      .catch(() => setBatchEvalCatalog({ providers: [], models: [] }));
  };

  return (
    <>
      <div className="indexer-tester">
        {testerError && <div className="indexer-tester-error">Error: {testerError}</div>}
        <div className="indexer-tester-layout">
          <div className="indexer-tester-sources">
            <h3>Indexer Tester</h3>
            {testerLoading ? (
              <div className="indexer-tester-loading">Loading sources...</div>
            ) : testerSources.length === 0 ? (
              <div className="indexer-tester-empty">No sources with markdown pages found.</div>
            ) : (
              <>
                <label className="indexer-select-label">
                  Source:
                  <select
                    value={testerSelectedSourceId}
                    onChange={(e) => setTesterSelectedSourceId(e.target.value)}
                    aria-label="Select source for Indexer Tester"
                  >
                    {testerSources.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.id} ({s.page_count} pages)
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="indexer-tester-btn primary"
                  onClick={openBatchEvalModal}
                  aria-label="Open Batch LLM Evaluation"
                >
                  Batch LLM Evaluation
                </button>
              </>
            )}
          </div>
          <div className="indexer-tester-files">
            <h4>Markdown files</h4>
            {testerFilesLoading ? (
              <div className="indexer-tester-loading">Loading files...</div>
            ) : !testerFiles.length ? (
              <div className="indexer-tester-empty">No .md files found for this source.</div>
            ) : (
              <table className="indexer-files-table" role="table" aria-label="Indexer tester files">
                <thead>
                  <tr>
                    <th>
                      <button type="button" className="indexer-sort-button" onClick={() => handleTesterSort('name')}>
                        Filename
                        {testerSortBy === 'name' && (
                          <span className="indexer-sort-indicator">{testerSortOrder === 'asc' ? ' ▲' : ' ▼'}</span>
                        )}
                      </button>
                    </th>
                    <th className="indexer-size-column">
                      <button type="button" className="indexer-sort-button" onClick={() => handleTesterSort('size')}>
                        Size (KB)
                        {testerSortBy === 'size' && (
                          <span className="indexer-sort-indicator">{testerSortOrder === 'asc' ? ' ▲' : ' ▼'}</span>
                        )}
                      </button>
                    </th>
                    <th>Inspect</th>
                  </tr>
                </thead>
                <tbody>
                  {testerFiles.map((file) => (
                    <tr key={file.filename}>
                      <td>{file.filename}</td>
                      <td className="indexer-size-column">{(file.size_bytes / 1024).toFixed(1)}</td>
                      <td>
                        <button type="button" className="indexer-tester-btn small" onClick={() => handleTesterSelectFile(file)}>
                          View
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>

      {showIndexerDetailModal && (
        <div className="indexer-modal-overlay" onClick={handleCloseIndexerDetailModal}>
          <div className="indexer-modal-content indexer-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="indexer-modal-header">
              <h3>
                {testerSelectedFile ? `${testerSelectedSourceId} / ${testerSelectedFile}` : 'Indexer Tester — Details'}
              </h3>
              <button type="button" className="indexer-modal-close" onClick={handleCloseIndexerDetailModal} aria-label="Close">
                ×
              </button>
            </div>
            <div className="indexer-modal-body indexer-detail-modal-body">
              {testerDetailLoading ? (
                <div className="indexer-tester-loading">Loading details…</div>
              ) : testerFileDetail ? (
                <div className="indexer-detail-panels">
                  <div className="indexer-panel indexer-panel-collapsible">
                    <button
                      type="button"
                      className="indexer-panel-header"
                      onClick={() => toggleIndexerSection('original')}
                      aria-expanded={indexerSectionOpen.original}
                      aria-controls="indexer-section-original"
                    >
                      <span className="indexer-panel-chevron" aria-hidden>{indexerSectionOpen.original ? '▼' : '▶'}</span>
                      <h5>Original markdown</h5>
                    </button>
                    {indexerSectionOpen.original && (
                      <div id="indexer-section-original" className="indexer-panel-body">
                        <pre className="indexer-code-block indexer-code-block-full">{testerFileDetail.source_md}</pre>
                      </div>
                    )}
                  </div>
                  <div className="indexer-panel indexer-panel-collapsible" aria-label="Diff between original and processed markdown">
                    <button
                      type="button"
                      className="indexer-panel-header"
                      onClick={() => toggleIndexerSection('diff')}
                      aria-expanded={indexerSectionOpen.diff}
                      aria-controls="indexer-section-diff"
                    >
                      <span className="indexer-panel-chevron" aria-hidden>{indexerSectionOpen.diff ? '▼' : '▶'}</span>
                      <h5>Diff (removed lines highlighted)</h5>
                    </button>
                    {indexerSectionOpen.diff && (
                      <div id="indexer-section-diff" className="indexer-panel-body">
                        <div className="indexer-diff">
                          {computeIndexerDiff(testerFileDetail.source_md, testerFileDetail.processed_md).map((line) => (
                            <div
                              key={line.key}
                              className={`indexer-diff-line${
                                line.type === 'removed'
                                  ? ' indexer-diff-line-removed'
                                  : line.type === 'fence_added'
                                  ? ' indexer-diff-line-fence'
                                  : ''
                              }`}
                            >
                              {line.text || ' '}
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                  <div className="indexer-panel indexer-panel-collapsible">
                    <button
                      type="button"
                      className="indexer-panel-header"
                      onClick={() => toggleIndexerSection('processed')}
                      aria-expanded={indexerSectionOpen.processed}
                      aria-controls="indexer-section-processed"
                    >
                      <span className="indexer-panel-chevron" aria-hidden>{indexerSectionOpen.processed ? '▼' : '▶'}</span>
                      <h5>Processed markdown</h5>
                    </button>
                    {indexerSectionOpen.processed && (
                      <div id="indexer-section-processed" className="indexer-panel-body">
                        <pre className="indexer-code-block indexer-code-block-full">{testerFileDetail.processed_md}</pre>
                      </div>
                    )}
                  </div>
                  <div className="indexer-panel indexer-panel-collapsible">
                    <button
                      type="button"
                      className="indexer-panel-header"
                      onClick={() => toggleIndexerSection('llm')}
                      aria-expanded={indexerSectionOpen.llm}
                      aria-controls="indexer-section-llm"
                    >
                      <span className="indexer-panel-chevron" aria-hidden>{indexerSectionOpen.llm ? '▼' : '▶'}</span>
                      <h5>Evaluate with LLM</h5>
                    </button>
                    {indexerSectionOpen.llm && (
                      <div id="indexer-section-llm" className="indexer-panel-body">
                        {llmCatalog.providers.length > 0 && (
                          <label className="indexer-select-label">
                            Provider:
                            <select
                              value={llmSelectedProviderId}
                              onChange={(e) => {
                                const nextProviderId = e.target.value;
                                setLlmSelectedProviderId(nextProviderId);
                                const nextModels = (llmCatalog.models || []).filter(
                                  (m) => m.provider_id === nextProviderId,
                                );
                                setLlmSelectedModel(nextModels[0]?.id || nextModels[0]?.name || '');
                              }}
                              aria-label="Provider for evaluation"
                              disabled={llmEvaluateLoading}
                            >
                              {llmCatalog.providers.map((provider) => (
                                <option key={provider.provider_id} value={provider.provider_id}>
                                  {provider.title || provider.provider_id}
                                </option>
                              ))}
                            </select>
                          </label>
                        )}
                        {llmModels.length > 0 && (
                          <label className="indexer-select-label">
                            Model:
                            <select
                              value={llmSelectedModel}
                              onChange={(e) => setLlmSelectedModel(e.target.value)}
                              aria-label="Model for evaluation"
                              disabled={llmEvaluateLoading}
                            >
                              {llmModels.map((m) => (
                                <option key={m.id || m.name} value={m.id || m.name}>
                                  {m.name || m.id || m.model || '—'}
                                </option>
                              ))}
                            </select>
                          </label>
                        )}
                        <button
                          type="button"
                          className="indexer-tester-btn primary"
                          onClick={handleAskLlm}
                          disabled={llmEvaluateLoading || !testerFileDetail?.source_md}
                        >
                          {llmEvaluateLoading ? 'Evaluating…' : 'Ask LLM'}
                        </button>
                        {llmEvaluateError && <div className="indexer-tester-error">{llmEvaluateError}</div>}
                        {llmEvaluateReply != null && llmEvaluateReply !== '' && (
                          <div className="indexer-llm-reply" role="region" aria-label="LLM evaluation reply">
                            <pre className="indexer-code-block indexer-llm-reply-text">{llmEvaluateReply}</pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              ) : (
                <div className="indexer-tester-empty">No file selected or failed to load.</div>
              )}
            </div>
          </div>
        </div>
      )}

      {showBatchEvalModal && (
        <div className="indexer-modal-overlay" onClick={handleCloseBatchEvalModal}>
          <div className="indexer-modal-content indexer-detail-modal batch-eval-modal" onClick={(e) => e.stopPropagation()}>
            <div className="indexer-modal-header">
              <h3>Batch LLM Evaluation</h3>
              <button type="button" className="indexer-modal-close" onClick={handleCloseBatchEvalModal} aria-label="Close">×</button>
            </div>
            <div className="indexer-modal-body">
              {!batchEvalJobId ? (
                <>
                  <label className="indexer-select-label">
                    Source:
                    <select value={batchEvalSourceId} onChange={(e) => setBatchEvalSourceId(e.target.value)} aria-label="Source for batch evaluation">
                      {testerSources.map((s) => (
                        <option key={s.id} value={s.id}>{s.id} ({s.page_count} pages)</option>
                      ))}
                    </select>
                  </label>
                  <label className="indexer-select-label">
                    Provider:
                    <select
                      value={batchEvalProviderId}
                      onChange={(e) => {
                        const nextProviderId = e.target.value;
                        setBatchEvalProviderId(nextProviderId);
                        const nextModels = (batchEvalCatalog.models || []).filter(
                          (m) => m.provider_id === nextProviderId,
                        );
                        setBatchEvalModel(nextModels[0]?.id || nextModels[0]?.name || '');
                      }}
                      aria-label="Provider for batch evaluation"
                    >
                      {batchEvalCatalog.providers.map((provider) => (
                        <option key={provider.provider_id} value={provider.provider_id}>
                          {provider.title || provider.provider_id}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="indexer-select-label">
                    Model:
                    <select value={batchEvalModel} onChange={(e) => setBatchEvalModel(e.target.value)} aria-label="Model for batch evaluation">
                      <option value="">Default (RAG)</option>
                      {batchEvalModels.map((m) => (
                        <option key={m.id || m.name} value={m.id || m.name}>{m.name || m.id || m.model || '—'}</option>
                      ))}
                    </select>
                  </label>
                  <label className="indexer-select-label">
                    Number of files:
                    <input
                      type="number"
                      min={1}
                      max={500}
                      value={batchEvalCount}
                      onChange={(e) => setBatchEvalCount(Number(e.target.value) || 5)}
                      aria-label="Number of files to evaluate"
                    />
                    <span className="batch-eval-hint">(random files &gt; 1.1 KB, &gt; 200 chars after cleanup)</span>
                  </label>
                  <div className="batch-eval-limits">
                    <span className="batch-eval-limits-label">Context limits (chars, ~4 chars/token):</span>
                    <div className="batch-eval-limits-row">
                      <label className="indexer-select-label batch-eval-limit-field">
                        ORIGINAL:
                        <input
                          type="number"
                          min={1000}
                          max={500000}
                          value={evalLimits.original_max_chars}
                          onChange={(e) => setEvalLimitsAndSave((prev) => ({ ...prev, original_max_chars: Math.max(1000, Math.min(500000, Number(e.target.value) || 40000)) }))}
                          aria-label="Max chars for ORIGINAL block"
                        />
                      </label>
                      <label className="indexer-select-label batch-eval-limit-field">
                        PROCESSED:
                        <input
                          type="number"
                          min={1000}
                          max={500000}
                          value={evalLimits.processed_max_chars}
                          onChange={(e) => setEvalLimitsAndSave((prev) => ({ ...prev, processed_max_chars: Math.max(1000, Math.min(500000, Number(e.target.value) || 40000)) }))}
                          aria-label="Max chars for PROCESSED block"
                        />
                      </label>
                      <label className="indexer-select-label batch-eval-limit-field">
                        REMOVED:
                        <input
                          type="number"
                          min={1000}
                          max={500000}
                          value={evalLimits.removed_max_chars}
                          onChange={(e) => setEvalLimitsAndSave((prev) => ({ ...prev, removed_max_chars: Math.max(1000, Math.min(500000, Number(e.target.value) || 24000)) }))}
                          aria-label="Max chars for REMOVED block"
                        />
                      </label>
                    </div>
                  </div>
                  <button
                    type="button"
                    className="indexer-tester-btn primary"
                    onClick={handleStartBatchEval}
                    disabled={!batchEvalSourceId && !testerSelectedSourceId}
                  >
                    Start
                  </button>
                  {batchEvalStatus?.status === 'error' && batchEvalStatus?.error && (
                    <div className="indexer-tester-error">{batchEvalStatus.error}</div>
                  )}
                </>
              ) : (
                <>
                  <div className="batch-eval-progress" role="status" aria-live="polite">
                    {batchEvalStatus?.total > 0 && (
                      <div className="batch-eval-progress-bar" aria-label={`Progress ${batchEvalStatus.done} of ${batchEvalStatus.total} files`}>
                        {Array.from({ length: batchEvalStatus.total }, (_, i) => (
                          <div
                            key={i}
                            className={`batch-eval-progress-segment ${i < batchEvalStatus.done ? 'filled' : ''} ${batchEvalStatus.status === 'running' && i === batchEvalStatus.done ? 'current' : ''}`}
                            title={i < batchEvalStatus.done ? `Done ${i + 1}` : i === batchEvalStatus.done ? 'In progress' : `Pending ${i + 1}`}
                          />
                        ))}
                      </div>
                    )}
                    {batchEvalStatus?.status === 'running' && (
                      <p className="batch-eval-progress-text">
                        {batchEvalStatus.done} / {batchEvalStatus.total} files
                        {batchEvalStatus.current_file && <span className="batch-eval-current"> — {batchEvalStatus.current_file}</span>}
                      </p>
                    )}
                    {batchEvalStatus?.status === 'done' && (
                      <p className="batch-eval-progress-text">Done: {batchEvalStatus.done} / {batchEvalStatus.total} files evaluated.</p>
                    )}
                    {batchEvalStatus?.status === 'error' && batchEvalStatus?.error && (
                      <div className="indexer-tester-error">{batchEvalStatus.error}</div>
                    )}
                  </div>
                  {batchEvalStatus?.status === 'done' && (batchEvalStatus?.results || []).length > 0 && (
                    <div className="batch-eval-patterns-block">
                      <button
                        type="button"
                        className="indexer-tester-btn primary"
                        onClick={handleDetectBatchPatterns}
                        disabled={batchEvalPatternsLoading}
                        aria-label="Detect cross-document patterns"
                      >
                        {batchEvalPatternsLoading ? 'Analyzing…' : 'Detect patterns'}
                      </button>
                      {batchEvalPatterns != null && batchEvalPatterns !== '' && (
                        <div className="batch-eval-patterns-result">
                          <h4>Patterns & suggested steps</h4>
                          <pre className="batch-eval-reply indexer-code-block">{batchEvalPatterns}</pre>
                        </div>
                      )}
                    </div>
                  )}
                  <div className="batch-eval-results">
                    <h4>Results</h4>
                    <ul className="batch-eval-list" aria-label="Batch evaluation results">
                      {(batchEvalStatus?.results || []).map((item, idx) => (
                        <li key={item.filename + String(idx)} className="batch-eval-item">
                          <div className="batch-eval-item-header">
                            <span className="batch-eval-filename">{item.filename}</span>
                            <button
                              type="button"
                              className="indexer-tester-btn small"
                              onClick={() => handleViewProcessed(item.filename)}
                              aria-label={`View processed content for ${item.filename}`}
                              title="View processed .md (pipeline output)"
                            >
                              View processed
                            </button>
                          </div>
                          <pre className="batch-eval-reply indexer-code-block">
                            {item.reply != null && item.reply !== '' ? item.reply : '(no response)'}
                          </pre>
                        </li>
                      ))}
                    </ul>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

      {batchEvalViewProcessed && (
        <div className="indexer-modal-overlay batch-eval-view-processed-overlay" onClick={() => setBatchEvalViewProcessed(null)}>
          <div className="indexer-modal-content indexer-detail-modal batch-eval-view-processed-modal" onClick={(e) => e.stopPropagation()}>
            <div className="indexer-modal-header">
              <h3>Processed content — {batchEvalViewProcessed.filename}</h3>
              <button type="button" className="indexer-modal-close" onClick={() => setBatchEvalViewProcessed(null)} aria-label="Close">×</button>
            </div>
            <div className="indexer-modal-body">
              {batchEvalViewProcessed.loading && <p className="batch-eval-view-loading">Loading…</p>}
              {batchEvalViewProcessed.error && <div className="indexer-tester-error">{batchEvalViewProcessed.error}</div>}
              {!batchEvalViewProcessed.loading && !batchEvalViewProcessed.error && batchEvalViewProcessed.processed_md != null && (
                <>
                  <div className="batch-eval-view-toolbar">
                    <button type="button" className="indexer-tester-btn primary" onClick={handleDownloadProcessedMd} aria-label="Download as Markdown file">
                      Download .md
                    </button>
                  </div>
                  <pre className="batch-eval-view-content indexer-code-block">{batchEvalViewProcessed.processed_md}</pre>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default IndexerTester;
