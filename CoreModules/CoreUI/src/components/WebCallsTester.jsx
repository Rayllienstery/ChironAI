import { useMemo, useState } from 'react';
import { previewExternalDocs } from '../services/api';
import '../styles/components/IndexerTester.css';
import '../styles/components/WebCallsTester.css';

function computeLineDiff(sourceText, processedText) {
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
      lines.push({ key: i, type: 'same', text: src });
    } else if (dst && dstIsFence && src !== dst) {
      lines.push({ key: i, type: 'fence_added', text: `+ ${dst}` });
    } else if (src) {
      lines.push({ key: i, type: 'removed', text: `- ${src}` });
    } else if (dst) {
      lines.push({ key: i, type: 'same', text: dst });
    }
  }
  return lines;
}

function WebCallsTester() {
  const [library, setLibrary] = useState('');
  const [maxFiles, setMaxFiles] = useState(10);
  const [maxCharsPerFile, setMaxCharsPerFile] = useState(80000);

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [result, setResult] = useState(null);

  const [selectedDoc, setSelectedDoc] = useState(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [sectionOpen, setSectionOpen] = useState({
    raw: false,
    diff: true,
    processed: true,
  });

  const resolved = result?.resolved || null;
  const documents = result?.documents || [];

  const canRun = !loading && (library || '').trim().length > 0;

  const handleRun = async () => {
    const name = (library || '').trim();
    if (!name) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setSelectedDoc(null);
    setShowDetailModal(false);
    try {
      const data = await previewExternalDocs({
        library: name,
        maxFiles,
        maxCharsPerFile,
      });
      setResult(data);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleOpenDoc = (doc) => {
    setSelectedDoc(doc);
    setShowDetailModal(true);
    setSectionOpen({ raw: false, diff: true, processed: true });
  };

  const handleCloseDoc = () => setShowDetailModal(false);

  const diffLines = useMemo(() => {
    if (!selectedDoc) return [];
    return computeLineDiff(selectedDoc.raw_md, selectedDoc.processed_md);
  }, [selectedDoc]);

  const toggleSection = (key) => setSectionOpen((prev) => ({ ...prev, [key]: !prev[key] }));

  const found = Boolean(resolved?.found);
  const primaryUrl = resolved?.primary_url || null;

  return (
    <div className="webcalls-tester">
      <div className="webcalls-tester-header">
        <h3>External docs web calls</h3>
        <div className="webcalls-tester-controls" role="region" aria-label="External docs tester controls">
          <label className="webcalls-label">
            Library:
            <input
              type="text"
              value={library}
              onChange={(e) => setLibrary(e.target.value)}
              placeholder="e.g. Alamofire"
              aria-label="Library name"
              disabled={loading}
            />
          </label>
          <label className="webcalls-label">
            Max files:
            <input
              type="number"
              min={1}
              max={50}
              value={maxFiles}
              onChange={(e) => setMaxFiles(Math.max(1, Math.min(50, Number(e.target.value) || 10)))}
              aria-label="Max files to fetch"
              disabled={loading}
            />
          </label>
          <label className="webcalls-label">
            Max chars/file:
            <input
              type="number"
              min={2000}
              max={300000}
              value={maxCharsPerFile}
              onChange={(e) =>
                setMaxCharsPerFile(Math.max(2000, Math.min(300000, Number(e.target.value) || 80000)))
              }
              aria-label="Max chars per file"
              disabled={loading}
            />
          </label>
          <button type="button" className="indexer-tester-btn primary" onClick={handleRun} disabled={!canRun}>
            {loading ? 'Running…' : 'Run'}
          </button>
        </div>
      </div>

      {error && <div className="indexer-tester-error">Error: {error}</div>}

      {result && (
        <div className="webcalls-result" role="region" aria-label="External docs result">
          <div className="webcalls-result-summary">
            <div className={`webcalls-badge ${found ? 'ok' : 'fail'}`}>
              {found ? 'Found' : 'Not found'}
            </div>
            {found && resolved?.repo_full_name && (
              <div className="webcalls-summary-item">
                <span className="webcalls-summary-label">Repo</span>
                <span className="webcalls-summary-value">{resolved.repo_full_name}</span>
              </div>
            )}
            {primaryUrl && (
              <div className="webcalls-summary-item">
                <span className="webcalls-summary-label">Primary URL</span>
                <a
                  className="webcalls-summary-link"
                  href={primaryUrl}
                  target="_blank"
                  rel="noreferrer"
                >
                  {primaryUrl}
                </a>
              </div>
            )}
            <div className="webcalls-summary-item">
              <span className="webcalls-summary-label">Pipeline</span>
              <span className="webcalls-summary-value">{result?.pipeline?.name || '(default)'}</span>
            </div>
          </div>

          <div className="webcalls-files">
            <h4>Files</h4>
            {!documents.length ? (
              <div className="indexer-tester-empty">No markdown files fetched.</div>
            ) : (
              <table className="webcalls-files-table" role="table" aria-label="Fetched markdown files">
                <thead>
                  <tr>
                    <th>Filename</th>
                    <th>Status</th>
                    <th>Inspect</th>
                  </tr>
                </thead>
                <tbody>
                  {documents.map((doc) => (
                    <tr key={doc.url || doc.filename}>
                      <td className="webcalls-filename">
                        {doc.url ? (
                          <a href={doc.url} target="_blank" rel="noreferrer">
                            {doc.filename}
                          </a>
                        ) : (
                          doc.filename
                        )}
                      </td>
                      <td>
                        {doc.error ? (
                          <span className="webcalls-status error" title={doc.error}>
                            error
                          </span>
                        ) : (
                          <span className="webcalls-status ok">ok</span>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="indexer-tester-btn small"
                          onClick={() => handleOpenDoc(doc)}
                          disabled={!doc.raw_md && !doc.processed_md}
                        >
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
      )}

      {showDetailModal && selectedDoc && (
        <div className="indexer-modal-overlay" onClick={handleCloseDoc}>
          <div className="indexer-modal-content indexer-detail-modal" onClick={(e) => e.stopPropagation()}>
            <div className="indexer-modal-header">
              <h3>{selectedDoc.filename || 'Document'}</h3>
              <button type="button" className="indexer-modal-close" onClick={handleCloseDoc} aria-label="Close">
                ×
              </button>
            </div>
            <div className="indexer-modal-body indexer-detail-modal-body">
              {selectedDoc.error && (
                <div className="indexer-tester-error" role="alert">
                  {selectedDoc.error}
                </div>
              )}
              <div className="indexer-detail-panels">
                <div className="indexer-panel indexer-panel-collapsible">
                  <button
                    type="button"
                    className="indexer-panel-header"
                    onClick={() => toggleSection('raw')}
                    aria-expanded={sectionOpen.raw}
                    aria-controls="webcalls-section-raw"
                  >
                    <span className="indexer-panel-chevron" aria-hidden>
                      {sectionOpen.raw ? '▼' : '▶'}
                    </span>
                    <h5>Raw markdown</h5>
                  </button>
                  {sectionOpen.raw && (
                    <div id="webcalls-section-raw" className="indexer-panel-body">
                      <pre className="indexer-code-block indexer-code-block-full">{selectedDoc.raw_md}</pre>
                    </div>
                  )}
                </div>

                <div className="indexer-panel indexer-panel-collapsible" aria-label="Diff between raw and processed markdown">
                  <button
                    type="button"
                    className="indexer-panel-header"
                    onClick={() => toggleSection('diff')}
                    aria-expanded={sectionOpen.diff}
                    aria-controls="webcalls-section-diff"
                  >
                    <span className="indexer-panel-chevron" aria-hidden>
                      {sectionOpen.diff ? '▼' : '▶'}
                    </span>
                    <h5>Diff (removed lines highlighted)</h5>
                  </button>
                  {sectionOpen.diff && (
                    <div id="webcalls-section-diff" className="indexer-panel-body">
                      <div className="indexer-diff">
                        {diffLines.map((line) => (
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
                    onClick={() => toggleSection('processed')}
                    aria-expanded={sectionOpen.processed}
                    aria-controls="webcalls-section-processed"
                  >
                    <span className="indexer-panel-chevron" aria-hidden>
                      {sectionOpen.processed ? '▼' : '▶'}
                    </span>
                    <h5>Processed markdown</h5>
                  </button>
                  {sectionOpen.processed && (
                    <div id="webcalls-section-processed" className="indexer-panel-body">
                      <pre className="indexer-code-block indexer-code-block-full">{selectedDoc.processed_md}</pre>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default WebCallsTester;

