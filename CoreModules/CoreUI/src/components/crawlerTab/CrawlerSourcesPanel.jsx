import React from "react";
import EmptyState from "../EmptyState";
import { t } from "../../services/i18n.js";
import { formatDate } from "./helpers";

export default function CrawlerSourcesPanel({
  loading,
  sources,
  selectedSource,
  sourcePages,
  selectedSourceIds,
  crawlingSources,
  onToggleSelectAll,
  onToggleSourceSelected,
  onSourceClick,
  onEditSource,
  onCrawlSource,
}) {
  if (loading) {
    return <div className="loading">{t('crawler.loading_sources')}</div>;
  }
  if (!sources.length) {
    return (
      <EmptyState className="empty-state">
        {t('crawler.empty_sources')}
      </EmptyState>
    );
  }
  return (
            <div className="crawler-sources" data-tour="crawler-sources">
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
                        checked={
                          sources.length > 0 &&
                          sources.every((s) => selectedSourceIds.has(s.id))
                        }
                        onChange={onToggleSelectAll}
                      />
                    </th>
                    <th>Source ID</th>
                    <th>URL</th>
                    <th>Last Crawled</th>
                    <th>Total Pages</th>
                    <th>Indexed</th>
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
                            onChange={() => onToggleSourceSelected(source.id)}
                          />
                        </td>
                        <td>{source.id}</td>
                         <td className="url-cell">{source.url || "—"}</td>
                        <td>{formatDate(source.last_crawled)}</td>
                        <td>{source.total_pages || 0}</td>
                        <td>
                          <span
                            className={`status-badge ${source.indexed_pages > 0 ? "indexed" : "not-indexed"}`}
                          >
                            {source.indexed_pages || 0}
                          </span>
                        </td>
                        <td>
                          <div className="source-actions">
                             <button
                               type="button"
                               className="crawler-button small"
                               onClick={() => onSourceClick(source.id)}
                             >
                               <span className="material-symbols-outlined" style={{ fontSize: '16px', marginRight: '4px', verticalAlign: 'middle' }}>
                                 {selectedSource === source.id ? "visibility_off" : "visibility"}
                               </span>
                               {selectedSource === source.id ? "Hide" : "View"} Details
                             </button>
                            <button
                              type="button"
                              className="crawler-button small"
                              onClick={() => onEditSource(source.id)}
                              title="Edit source configuration"
                            >
                              <span className="material-symbols-outlined" style={{ fontSize: '16px', marginRight: '4px', verticalAlign: 'middle' }}>edit</span> Edit
                            </button>
                            <button
                              type="button"
                              className="crawler-button small refresh"
                              onClick={() => onCrawlSource(source.id)}
                              disabled={crawlingSources.has(source.id)}
                              title="Refresh/Crawl this source"
                            >
                              {crawlingSources.has(source.id) ? (
                                <>
                                  <span className="spinner"></span> Crawling...
                                </>
                                ) : (
                                  <>
                                    <span className="material-symbols-outlined" style={{ fontSize: '16px', marginRight: '4px', verticalAlign: 'middle' }}>refresh</span> Refresh
                                  </>
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
                                  <span className="detail-label">
                                    Source ID:
                                  </span>
                                  <span className="detail-value">
                                    {source.id}
                                  </span>
                                </div>
                                {source.max_depth && (
                                  <div className="detail-item">
                                    <span className="detail-label">
                                      Max Depth:
                                    </span>
                                    <span className="detail-value">
                                      {source.max_depth}
                                    </span>
                                  </div>
                                )}
                                {source.crawler && (
                                  <div className="detail-item">
                                    <span className="detail-label">
                                      Crawler:
                                    </span>
                                    <span className="detail-value">
                                      {source.crawler}
                                    </span>
                                  </div>
                                )}
                                {source.seed_urls &&
                                  source.seed_urls.length > 0 && (
                                    <div className="detail-item full-width">
                                      <span className="detail-label">
                                        Seed URLs:
                                      </span>
                                      <ul className="seed-urls-list">
                                        {source.seed_urls
                                          .slice(0, 10)
                                          .map((url, idx) => (
                                            <li key={idx}>{url}</li>
                                          ))}
                                        {source.seed_urls.length > 10 && (
                                          <li className="more-urls">
                                            ... and{" "}
                                            {source.seed_urls.length - 10} more
                                          </li>
                                        )}
                                      </ul>
                                    </div>
                                  )}
                              </div>
                              {sourcePages.length > 0 && (
                                <div className="pages-section">
                                  <h5>
                                    Recent Pages ({sourcePages.length} total)
                                  </h5>
                                  <div className="pages-list">
                                    {sourcePages
                                      .slice(0, 20)
                                      .map((page, idx) => (
                                        <div key={idx} className="page-item">
                                          <span className="page-filename">
                                            {page.filename}
                                          </span>
                                          <span className="page-url">
                                            {page.url}
                                          </span>
                                          {page.has_chunks && (
                                            <span className="page-chunks">
                                              {page.chunk_count} chunks
                                            </span>
                                          )}
                                        </div>
                                      ))}
                                    {sourcePages.length > 20 && (
                                      <div className="more-pages">
                                        ... and {sourcePages.length - 20} more
                                        pages
                                      </div>
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
  );
}
