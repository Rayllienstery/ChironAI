import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { getLogs, getProxyLogs, clearLogs, clearProxyLogs } from '../services/api';
import { startLogPolling, stopLogPolling } from '../services/logs';
import ProxyLogsAnalytics, { getMetadata } from './ProxyLogsAnalytics';
import '../styles/components/CoreUIButtons.css';
import '../styles/components/LogsTab.css';
import '../styles/components/CoreUIPillTabs.css';

const PROXY_LOGS_ANALYTICS_LIMIT = 5000;

function getDateRangeForProxyLogs(period, selectedDate) {
  const now = new Date();
  if (selectedDate) {
    const d = new Date(selectedDate.getFullYear(), selectedDate.getMonth(), selectedDate.getDate());
    const from = new Date(d);
    from.setHours(0, 0, 0, 0);
    const to = new Date(d);
    to.setHours(23, 59, 59, 999);
    return { from: from.toISOString(), to: to.toISOString() };
  }
  switch (period) {
    case 'day': {
      const start = new Date(now);
      start.setHours(0, 0, 0, 0);
      return { from: start.toISOString(), to: now.toISOString() };
    }
    case 'week': {
      const start = new Date(now);
      start.setDate(start.getDate() - 6);
      start.setHours(0, 0, 0, 0);
      return { from: start.toISOString(), to: now.toISOString() };
    }
    case 'month': {
      const start = new Date(now.getFullYear(), now.getMonth(), 1);
      return { from: start.toISOString(), to: now.toISOString() };
    }
    case 'year': {
      const start = new Date(now.getFullYear(), 0, 1);
      return { from: start.toISOString(), to: now.toISOString() };
    }
    default:
      return {};
  }
}

function getPeriodLabel(period, selectedDate) {
  const formatDate = (date) => date.toLocaleDateString(undefined, { day: 'numeric', month: 'long', year: 'numeric' });
  if (selectedDate) {
    return formatDate(selectedDate);
  }
  const now = new Date();
  switch (period) {
    case 'day':
      return formatDate(now);
    case 'week': {
      const weekStart = new Date(now);
      weekStart.setDate(weekStart.getDate() - 6);
      return `${formatDate(weekStart)} – ${formatDate(now)}`;
    }
    case 'month':
      return now.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
    case 'year':
      return String(now.getFullYear());
    default:
      return 'All time';
  }
}

function LogsTab({ sessionId }) {
  const [viewMode, setViewMode] = useState('logs'); // 'logs' | 'proxy' | 'autocomplete'
  const [logs, setLogs] = useState([]);
  const [levelFilter, setLevelFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const [period, setPeriod] = useState('day');
  const [selectedDate, setSelectedDate] = useState(null);
  const [pipelineFilter, setPipelineFilter] = useState('mixed');
  const logsEndRef = useRef(null);

  const displayProxyLogs = useMemo(() => {
    if (viewMode !== 'proxy') return logs;
    if (pipelineFilter === 'mixed') return logs;
    if (pipelineFilter === 'rag_fusion') {
      return logs.filter((log) => getMetadata(log).proxy_backend === 'rag_fusion');
    }
    return logs;
  }, [logs, viewMode, pipelineFilter]);

  const scrollToBottom = () => {
    const container = document.querySelector('.logs-content');
    if (container) {
      const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 150;
      if (isNearBottom) {
        logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
      }
    } else {
      logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  };

  const loadLogs = useCallback(async () => {
    setLoading(true);
    try {
      if (viewMode === 'proxy' || viewMode === 'autocomplete') {
        const { from, to } = getDateRangeForProxyLogs(period, selectedDate);
        const data = await getProxyLogs({
          from: from || undefined,
          to: to || undefined,
          limit: PROXY_LOGS_ANALYTICS_LIMIT,
          autocompleteOnly: viewMode === 'autocomplete',
        });
        const newLogs = data.logs || [];
        setLogs((prev) => {
          const hadNewLogs = prev.length > 0 && newLogs.length > prev.length;
          if (prev.length === 0 || hadNewLogs) setTimeout(() => scrollToBottom(), 100);
          return newLogs;
        });
      } else {
        if (!sessionId) return;
        const data = await getLogs(sessionId, {
          level: levelFilter || undefined,
          source: sourceFilter || undefined,
          limit: 100,
        });
        const newLogs = data.logs || [];
        setLogs((prev) => {
          const hadNewLogs = prev.length > 0 && newLogs.length > prev.length;
          if (prev.length === 0 || hadNewLogs) setTimeout(() => scrollToBottom(), 100);
          return newLogs;
        });
      }
    } catch (error) {
      console.error('Failed to load logs:', error);
    } finally {
      setLoading(false);
    }
  }, [viewMode, period, selectedDate, sessionId, levelFilter, sourceFilter]);

  const handleClearLogs = useCallback(async () => {
    try {
      if (viewMode === 'logs') {
        if (!sessionId) return;
        await clearLogs(sessionId);
      } else if (viewMode === 'proxy') {
        await clearProxyLogs({});
      } else if (viewMode === 'autocomplete') {
        await clearProxyLogs({ autocompleteOnly: true });
      }
      setLogs([]);
      await loadLogs();
    } catch (error) {
      console.error('Failed to clear logs:', error);
    }
  }, [viewMode, sessionId, loadLogs]);

  useEffect(() => {
    if (viewMode === 'logs' && !sessionId) return;

    loadLogs();

    if (viewMode === 'logs' && sessionId) {
      startLogPolling(sessionId, (newLogs) => {
        setLogs(prev => {
          const existingIds = new Set(prev.map(log => log.id));
          const uniqueNewLogs = newLogs.filter(log => !existingIds.has(log.id));
          const hadNewLogs = uniqueNewLogs.length > 0;
          const updated = [...prev, ...uniqueNewLogs].slice(-500);
          if (hadNewLogs) setTimeout(() => scrollToBottom(), 100);
          return updated;
        });
      }, 3000);
      return () => stopLogPolling();
    }
    if (viewMode === 'proxy' || viewMode === 'autocomplete') {
      const interval = setInterval(loadLogs, 3000);
      return () => clearInterval(interval);
    }
  }, [sessionId, levelFilter, viewMode, period, selectedDate, loadLogs]);

  const getLevelClass = (level) => {
    return `log-entry log-${level.toLowerCase()}`;
  };

  const getLevelIcon = (level) => {
    const lvl = (level || '').toUpperCase();
    if (lvl === 'ERROR') return '⛔';
    if (lvl === 'WARNING') return '';
    return 'ℹ️';
  };

  const buildTitle = (log) => {
    const level = log.level || '';
    const sourceRaw = log.source || '';
    const type = log.error_type || '';
    const msg = log.message || '';

    // Try to extract a short error code like "WinError 10061"
    let code = '';
    const winMatch = msg.match(/WinError\s+\d+/);
    if (winMatch) {
      code = winMatch[0];
    }

    const mainSource =
      sourceRaw === 'ollama'
        ? 'ollama'
        : (sourceRaw.split('.')[0] || 'unknown');

    const parts = [];
    if (code) {
      parts.push(`[${code}]`);
    }
    parts.push(`Source: ${mainSource}`);
    if (type || level) {
      parts.push(`Type: ${type || level}`);
    }
    return parts.join(' | ');
  };

  const buildMessage = (log) => {
    const msg = log.message || '';
    const idx = msg.indexOf('message=');
    if (idx === -1) {
      return msg;
    }
    const extracted = msg.slice(idx + 'message='.length).trim();
    return extracted;
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    try {
      return new Date(timestamp).toLocaleString();
    } catch {
      return timestamp;
    }
  };

  const renderProxyLog = (log) => {
    // Safely parse metadata
    let metadata = {};
    try {
      if (log.metadata) {
        if (typeof log.metadata === 'string') {
          metadata = JSON.parse(log.metadata);
        } else {
          metadata = log.metadata;
        }
      }
    } catch (e) {
      console.error('Failed to parse metadata:', e);
      metadata = {};
    }
    
    const isAc = Boolean(metadata.is_autocomplete);
    const backend = metadata.proxy_backend;
    const ragContext = metadata.rag_context || {};
    const chunksCount = ragContext.chunks_count || 0;
    const maxScore = ragContext.max_score;
    const chunksInfo = Array.isArray(ragContext.chunks_info) ? ragContext.chunks_info : [];
    
    return (
      <div key={log.id} className="log-entry log-info proxy-log-entry">
        <div className="log-header">
          <div className="log-title">
            <span className="log-icon">ℹ️</span>
            <span className="log-summary">Proxy Request</span>
            {isAc && (
              <span className="proxy-log-ac-badge" title="ChironAI-Autocomplete logical model">
                Autocomplete
              </span>
            )}
            {backend === 'rag_fusion' && (
              <span className="proxy-log-pipeline-badge proxy-log-pipeline-badge--rag" title="RAG Fusion (dumb) build">
                RAG Fusion
              </span>
            )}
          </div>
          <span className="log-timestamp">{formatTimestamp(log.timestamp)}</span>
        </div>
        <div className="proxy-log-content">
          <div className="proxy-log-section">
            <strong>User Query:</strong>
            <div className="proxy-log-text">{metadata.user_query || 'N/A'}</div>
          </div>
          <div className="proxy-log-section">
            <strong>Response Preview:</strong>
            <div className="proxy-log-text">{metadata.response_preview || 'N/A'}</div>
          </div>
          <div className="proxy-log-metrics">
            <div className="proxy-log-metric">
              <span className="metric-label">Model:</span>
              <span className="metric-value">{metadata.model || 'N/A'}</span>
            </div>
            <div className="proxy-log-metric">
              <span className="metric-label">Latency:</span>
              <span className="metric-value">{metadata.latency_ms || 0}ms</span>
            </div>
            <div className="proxy-log-metric">
              <span className="metric-label">Prompt Tokens:</span>
              <span className="metric-value">{metadata.prompt_tokens || 0}</span>
            </div>
            <div className="proxy-log-metric">
              <span className="metric-label">Completion Tokens:</span>
              <span className="metric-value">{metadata.completion_tokens || 0}</span>
            </div>
            <div className="proxy-log-metric">
              <span className="metric-label">Total Tokens:</span>
              <span className="metric-value">{metadata.total_tokens || 0}</span>
            </div>
          </div>
          {metadata.rag_steps && (
            <div className="proxy-log-section proxy-log-rag-steps">
              <strong>RAG steps (time)</strong>
              <span className="proxy-log-rag-hint"> — this request only</span>
              <div className="proxy-log-rag-steps-values">
                embed {Number(metadata.rag_steps.embed_s ?? 0).toFixed(2)}s
                {' | '}
                search {Number(metadata.rag_steps.search_s ?? 0).toFixed(2)}s
                {' | '}
                rerank {Number(metadata.rag_steps.rerank_s ?? 0).toFixed(2)}s
                {metadata.rag_steps.total_rag_s != null && (
                  <> (total RAG {Number(metadata.rag_steps.total_rag_s).toFixed(2)}s)</>
                )}
              </div>
            </div>
          )}
          {chunksCount > 0 && (
            <div className="proxy-log-section">
              <strong>RAG Context:</strong>
              <div className="proxy-log-rag-info">
                <div className="rag-metric">Chunks: {chunksCount}</div>
                <div className="rag-metric">
                  Max Score: {typeof maxScore === 'number' ? maxScore.toFixed(3) : (maxScore || 'N/A')}
                </div>
                <div className="rag-metric">Context Length: {ragContext.context_length || 0} chars</div>
                {chunksInfo.length > 0 && (
                  <div className="rag-chunks-preview">
                    <strong>Top Chunks ({chunksInfo.length}):</strong>
                    <div className="rag-chunks-list">
                      {chunksInfo.map((chunk, idx) => {
                        const chunkScore = chunk?.score;
                        const docType = chunk?.doc_type || 'N/A';
                        const url = chunk?.url || '';
                        const textLength = chunk?.text_length || 0;
                        const rerankScore = chunk?.rerank_score;
                        return (
                          <div key={idx} className="rag-chunk-item">
                            <div className="chunk-header">
                              <div className="chunk-left">
                                <span className="chunk-index">#{idx + 1}</span>
                                <span className="chunk-doc-type">{docType}</span>
                              </div>
                              <div className="chunk-right">
                                <span className="chunk-score-badge">
                                  <span className="score-label">Score:</span>
                                  <span className="score-value">
                                    {typeof chunkScore === 'number' ? chunkScore.toFixed(4) : (chunkScore || 'N/A')}
                                  </span>
                                </span>
                                {textLength > 0 && (
                                  <span className="chunk-length-badge">
                                    <span className="score-label">Length:</span>
                                    <span className="score-value">{textLength} chars</span>
                                  </span>
                                )}
                                {typeof rerankScore === 'number' && (
                                  <span className="chunk-rerank-badge">
                                    <span className="score-label">Rerank:</span>
                                    <span className="score-value">{rerankScore.toFixed(4)}</span>
                                  </span>
                                )}
                              </div>
                            </div>
                            {url && (
                              <div className="chunk-url-container">
                                <span className="chunk-url" title={url}>
                                  {url}
                                </span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="logs-tab">
      <div className="logs-header">
        <div className="logs-header-left">
          <h2>Logs</h2>
          <div className="coreui-pill-tablist" role="tablist" aria-label="Log source">
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === 'logs'}
              className={`coreui-pill-tab ${viewMode === 'logs' ? 'coreui-pill-tab-active' : ''}`}
              onClick={() => setViewMode('logs')}
            >
              Logs
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === 'proxy'}
              className={`coreui-pill-tab ${viewMode === 'proxy' ? 'coreui-pill-tab-active' : ''}`}
              onClick={() => setViewMode('proxy')}
            >
              Proxy Logs
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={viewMode === 'autocomplete'}
              className={`coreui-pill-tab ${viewMode === 'autocomplete' ? 'coreui-pill-tab-active' : ''}`}
              onClick={() => setViewMode('autocomplete')}
            >
              Autocomplete Logs
            </button>
          </div>
        </div>
        <div className="logs-controls">
          {viewMode === 'logs' && (
            <>
              <select
                value={levelFilter}
                onChange={(e) => setLevelFilter(e.target.value)}
              >
                <option value="">All Levels</option>
                <option value="ERROR">ERROR</option>
                <option value="WARNING">WARNING</option>
                <option value="INFO">INFO</option>
              </select>
              <select
                value={sourceFilter}
                onChange={(e) => setSourceFilter(e.target.value)}
              >
                <option value="">All Sources</option>
                <option value="ollama">Ollama</option>
                <option value="rag_routes.chat_completions">rag_routes</option>
                <option value="webui_routes">webui_routes</option>
              </select>
            </>
          )}
          <button
            type="button"
            className="coreui-btn"
            onClick={handleClearLogs}
            disabled={viewMode === 'logs' && !sessionId}
          >
            Clear
          </button>
          <button type="button" className="coreui-btn coreui-btn-ghost" onClick={loadLogs}>
            Refresh
          </button>
        </div>
      </div>

      {(viewMode === 'proxy' || viewMode === 'autocomplete') && (
        <ProxyLogsAnalytics
          logs={displayProxyLogs}
          period={period}
          onPeriodChange={setPeriod}
          selectedDate={selectedDate}
          onDateSelect={setSelectedDate}
          onDateReset={() => setSelectedDate(null)}
          periodLabel={getPeriodLabel(period, selectedDate)}
          variant={viewMode === 'autocomplete' ? 'autocomplete' : 'proxy'}
          pipelineFilter={pipelineFilter}
          onPipelineFilterChange={setPipelineFilter}
          showPipelineFilter={viewMode === 'proxy'}
        />
      )}

      <div className="logs-content">
        {viewMode === 'logs' && !sessionId ? (
          <div className="loading">No session available. Session is loading or could not be created.</div>
        ) : loading &&
          (viewMode === 'proxy' || viewMode === 'autocomplete' ? displayProxyLogs : logs).length === 0 ? (
          <div className="loading">
            Loading{' '}
            {viewMode === 'proxy' ? 'proxy ' : viewMode === 'autocomplete' ? 'autocomplete ' : ''}
            logs...
          </div>
        ) : (viewMode === 'proxy' || viewMode === 'autocomplete' ? displayProxyLogs : logs).length === 0 ? (
          <div className="empty-state">
            No{' '}
            {viewMode === 'proxy' ? 'proxy ' : viewMode === 'autocomplete' ? 'autocomplete ' : ''}
            logs found
          </div>
        ) : (
          (viewMode === 'proxy' || viewMode === 'autocomplete' ? displayProxyLogs : logs).map((log) => 
            viewMode === 'proxy' || viewMode === 'autocomplete' ? (
              renderProxyLog(log)
            ) : (
              <div key={log.id} className={getLevelClass(log.level)}>
                <div className="log-header">
                  <div className="log-title">
                    <span className="log-icon">{getLevelIcon(log.level)}</span>
                    <span className="log-summary">{buildTitle(log)}</span>
                  </div>
                  <span className="log-timestamp">{formatTimestamp(log.timestamp)}</span>
                </div>
                <div className="log-message">{buildMessage(log)}</div>
              </div>
            )
          )
        )}
        <div ref={logsEndRef} />
      </div>

    </div>
  );
}

export default LogsTab;


