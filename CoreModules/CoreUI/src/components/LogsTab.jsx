import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { getLogs, getProxyLogs, clearLogs, clearProxyLogs } from '../services/api';
import { startLogPolling, stopLogPolling } from '../services/logs';
import ProxyLogsAnalytics, {
  getMetadata,
  isClawPipelineLog,
  clawJournalUserPreview,
} from './ProxyLogsAnalytics';
import ClawCodeMarkIcon from './ClawCodeMarkIcon';
import ProxyTraceDetailModal from './ProxyTraceDetailModal';
import '../styles/components/CoreUIButtons.css';
import '../styles/components/LogsTab.css';
import '../styles/components/CoreUIPillTabs.css';
import '../styles/components/NotificationCenter.css';

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
  const [clawResponseModal, setClawResponseModal] = useState(null);
  const [clawTraceDetailLog, setClawTraceDetailLog] = useState(null);
  const logsEndRef = useRef(null);

  useEffect(() => {
    if (!clawResponseModal) return undefined;
    const onKey = (e) => {
      if (e.key === 'Escape') setClawResponseModal(null);
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [clawResponseModal]);

  const displayProxyLogs = useMemo(() => {
    if (viewMode !== 'proxy') return logs;
    if (pipelineFilter === 'mixed') return logs;
    if (pipelineFilter === 'claw') {
      return logs.filter((log) => isClawPipelineLog(log));
    }
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

  const renderClawJournalLog = (log) => {
    const meta = getMetadata(log);
    const tid = String(meta.trace_id || '').slice(0, 12) || '—';
    const model = meta.resolved_model || meta.client_model || meta.request?.model || 'N/A';
    const steps = Array.isArray(meta.steps) ? meta.steps : [];
    const rtc = meta.clawcode_runtime && typeof meta.clawcode_runtime === 'object' ? meta.clawcode_runtime : null;
    const sks = meta.skills && typeof meta.skills === 'object' ? meta.skills : null;
    const req = meta.request && typeof meta.request === 'object' ? meta.request : {};
    const clientToolNames = Array.isArray(req.client_tool_names) ? req.client_tool_names : [];

    const ragSteps = steps.filter((s) => s?.kind === 'tool_rag');
    const skillSteps = steps.filter((s) => s?.kind === 'tool_skill');

    const chunksInfo = [];
    for (const st of ragSteps) {
      if (Array.isArray(st.chunks_info)) {
        chunksInfo.push(...st.chunks_info);
      }
    }
    const chunksCount =
      chunksInfo.length ||
      ragSteps.reduce((acc, s) => acc + (Number(s.chunks) > 0 ? Number(s.chunks) : 0), 0);

    const tri = (v) => (v === true ? 'Yes' : v === false ? 'No' : '—');
    const enabledIds = Array.isArray(sks?.enabled_ids) ? sks.enabled_ids.map(String) : [];
    const showSkillIds = enabledIds.slice(0, 8);
    const skillIdsRest = enabledIds.length - showSkillIds.length;
    const loadedInv = Array.isArray(sks?.loaded_invocations) ? sks.loaded_invocations.map(String) : [];

    const ragUsed = ragSteps.length > 0;
    const skillsUsed = skillSteps.some((s) => s?.ok) || loadedInv.length > 0;
    const skillsToolsOff = rtc?.include_skill_tools === false;
    const showSkillsCatalog =
      !skillsToolsOff &&
      (enabledIds.length > 0 ||
        (sks?.enabled_count ?? 0) > 0 ||
        rtc?.include_skill_tools === true ||
        (!rtc && clientToolNames.includes('load_skill')));

    const fm =
      meta.final_message && typeof meta.final_message === 'object' ? meta.final_message : null;
    const resp =
      fm && typeof fm.content === 'string'
        ? fm.content
        : '';
    const contentTruncated = Boolean(fm?.content_truncated);
    const userLine = clawJournalUserPreview(meta);

    const openClawResponseModal = () => {
      if (resp) setClawResponseModal({ text: resp, traceShort: tid, contentTruncated });
    };

    return (
      <div
        key={log.id}
        className="log-entry log-info proxy-log-entry proxy-log-entry--claw-journal proxy-log-entry--claw-journal-open-detail"
        onClick={() => setClawTraceDetailLog(log)}
        title="Click to open trace detail"
        role="presentation"
      >
        <div className="log-header">
          <div className="log-title">
            <span className="log-icon log-icon--claw-mark" aria-hidden>
              <ClawCodeMarkIcon title="ClawCode" width={22} height={22} />
            </span>
            <span className="log-summary">ClawCode (direct)</span>
            <span className="proxy-log-pipeline-badge proxy-log-pipeline-badge--claw" title="ClawCode OpenAI port">
              Claw
            </span>
          </div>
          <span className="log-timestamp">{formatTimestamp(log.timestamp)}</span>
        </div>
        <div className="proxy-log-content">
          <div className="proxy-log-section">
            <strong>Trace:</strong> <code>{tid}</code>
            {meta.error && (
              <div className="proxy-log-text proxy-log-claw-error">{String(meta.error)}</div>
            )}
          </div>
          <div className="proxy-log-section claw-journal-runtime">
            <strong>RAG</strong>
            <div className="proxy-log-rag-info claw-journal-runtime-inner">
              <div className="claw-journal-kv">
                <span className="claw-journal-k">Tool registered</span>
                <span className="claw-journal-v">{tri(rtc?.include_rag_query_tool)}</span>
              </div>
              {rtc?.rag_collection_name ? (
                <div className="claw-journal-kv">
                  <span className="claw-journal-k">Collection override</span>
                  <span className="claw-journal-v">
                    <code>{String(rtc.rag_collection_name)}</code>
                  </span>
                </div>
              ) : null}
              {rtc?.rag_effective_collection ? (
                <div className="claw-journal-kv">
                  <span className="claw-journal-k">Qdrant collection</span>
                  <span className="claw-journal-v">
                    <code>{String(rtc.rag_effective_collection)}</code>
                  </span>
                </div>
              ) : null}
              {!rtc && clientToolNames.includes('rag_query') ? (
                <div className="claw-journal-kv claw-journal-kv--hint">
                  <span className="claw-journal-k">Request tools</span>
                  <span className="claw-journal-v">includes <code>rag_query</code> (runtime flags not stored)</span>
                </div>
              ) : null}
              <div className="claw-journal-kv">
                <span className="claw-journal-k">Used in trace</span>
                <span className={`claw-journal-v claw-journal-flag ${ragUsed ? 'claw-journal-flag--yes' : 'claw-journal-flag--no'}`}>
                  {ragUsed ? `Yes (${ragSteps.length} call${ragSteps.length === 1 ? '' : 's'})` : 'No'}
                </span>
              </div>
              {chunksCount > 0 ? (
                <div className="claw-journal-kv">
                  <span className="claw-journal-k">Chunk refs (total)</span>
                  <span className="claw-journal-v">{chunksInfo.length || chunksCount}</span>
                </div>
              ) : null}
              {ragSteps.length > 0 ? (
                <ul className="claw-journal-step-list">
                  {ragSteps.map((rs, i) => (
                    <li key={`rag-${i}-${rs.step ?? i}`} className="claw-journal-step-item">
                      <span className={rs.ok === false ? 'claw-journal-err' : ''}>
                        {rs.ok === false ? '✗' : '✓'} {String(rs.query || '(empty query)').slice(0, 120)}
                        {String(rs.query || '').length > 120 ? '…' : ''}
                      </span>
                      <span className="claw-journal-step-meta">
                        chunks {rs.chunks ?? 0}
                        {rs.max_score != null ? ` · max ${Number(rs.max_score).toFixed(3)}` : ''}
                        {rs.duration_ms != null ? ` · ${rs.duration_ms}ms` : ''}
                      </span>
                      {rs.error ? (
                        <div className="claw-journal-err claw-journal-step-err">{String(rs.error)}</div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
          <div className="proxy-log-section claw-journal-runtime">
            <strong>Skills</strong>
            <div className="proxy-log-rag-info claw-journal-runtime-inner">
              <div className="claw-journal-kv">
                <span className="claw-journal-k">Tool registered</span>
                <span className="claw-journal-v">{tri(rtc?.include_skill_tools)}</span>
              </div>
              {!rtc && clientToolNames.includes('load_skill') ? (
                <div className="claw-journal-kv claw-journal-kv--hint">
                  <span className="claw-journal-k">Request tools</span>
                  <span className="claw-journal-v">includes <code>load_skill</code> (runtime flags not stored)</span>
                </div>
              ) : null}
              {showSkillsCatalog ? (
                <div className="claw-journal-kv">
                  <span className="claw-journal-k">Enabled packs</span>
                  <span className="claw-journal-v">
                    {sks?.enabled_count != null ? sks.enabled_count : enabledIds.length}
                    {showSkillIds.length > 0 ? (
                      <>
                        {' '}
                        <span className="claw-journal-id-list">
                          ({showSkillIds.map((id) => (
                            <code key={id}>{id}</code>
                          ))}
                          {skillIdsRest > 0 ? ` +${skillIdsRest} more` : ''})
                        </span>
                      </>
                    ) : null}
                  </span>
                </div>
              ) : null}
              <div className="claw-journal-kv">
                <span className="claw-journal-k">Loaded (SKILL.md)</span>
                <span className={`claw-journal-v claw-journal-flag ${skillsUsed ? 'claw-journal-flag--yes' : 'claw-journal-flag--no'}`}>
                  {loadedInv.length > 0
                    ? loadedInv.join(', ')
                    : skillSteps.length > 0
                      ? 'No successful load'
                      : 'None'}
                </span>
              </div>
              {skillSteps.length > 0 ? (
                <ul className="claw-journal-step-list">
                  {skillSteps.map((ss, i) => (
                    <li key={`sk-${i}-${ss.step ?? i}`} className="claw-journal-step-item">
                      <span className={ss.ok === false ? 'claw-journal-err' : ''}>
                        {ss.ok === false ? '✗' : '✓'} {String(ss.invocation || ss.skill_id || 'load_skill').slice(0, 120)}
                      </span>
                      {ss.skill_id ? (
                        <span className="claw-journal-step-meta">
                          id <code>{String(ss.skill_id)}</code>
                          {ss.duration_ms != null ? ` · ${ss.duration_ms}ms` : ''}
                        </span>
                      ) : ss.duration_ms != null ? (
                        <span className="claw-journal-step-meta">{ss.duration_ms}ms</span>
                      ) : null}
                      {ss.error ? (
                        <div className="claw-journal-err claw-journal-step-err">{String(ss.error)}</div>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
          <div className="proxy-log-section">
            <strong>Request preview:</strong>
            <div className="proxy-log-text">{userLine}</div>
          </div>
          <div
            className={`proxy-log-section${resp ? ' proxy-log-section--claw-response-clickable' : ''}`}
            role={resp ? 'button' : undefined}
            tabIndex={resp ? 0 : undefined}
            onClick={(e) => {
              e.stopPropagation();
              openClawResponseModal();
            }}
            onKeyDown={(e) => {
              if (!resp) return;
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                e.stopPropagation();
                openClawResponseModal();
              }
            }}
          >
            <strong>Response preview:</strong>
            {resp ? (
              <div
                className="proxy-log-text proxy-log-text--claw-response-preview"
                title="Click to open full response"
              >
                {`${resp.slice(0, 500)}${resp.length > 500 ? '…' : ''}`}
              </div>
            ) : (
              <div className="proxy-log-text">N/A</div>
            )}
          </div>
          <div className="proxy-log-metrics">
            <div className="proxy-log-metric">
              <span className="metric-label">Model:</span>
              <span className="metric-value">{model}</span>
            </div>
            <div className="proxy-log-metric">
              <span className="metric-label">Latency:</span>
              <span className="metric-value">{meta.elapsed_ms != null ? `${meta.elapsed_ms}ms` : 'N/A'}</span>
            </div>
            <div className="proxy-log-metric">
              <span className="metric-label">Steps:</span>
              <span className="metric-value">{meta.step_count ?? steps.length}</span>
            </div>
            <div className="proxy-log-metric">
              <span className="metric-label">Tokens (est.):</span>
              <span className="metric-value">
                {meta.total_prompt_tokens_est != null || meta.total_completion_tokens_est != null
                  ? `${meta.total_prompt_tokens_est ?? '—'} / ${meta.total_completion_tokens_est ?? '—'}`
                  : 'N/A'}
              </span>
            </div>
          </div>
        </div>
      </div>
    );
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
            {backend === 'claw' && (
              <span className="proxy-log-pipeline-badge proxy-log-pipeline-badge--claw" title="Claw build forward">
                Claw
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
              log.session_id === 'clawcode' ? renderClawJournalLog(log) : renderProxyLog(log)
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

      <ProxyTraceDetailModal
        log={clawTraceDetailLog}
        isOpen={Boolean(clawTraceDetailLog)}
        onClose={() => setClawTraceDetailLog(null)}
      />

      {clawResponseModal ? (
        <div
          className="logs-tab-modal-overlay"
          onClick={() => setClawResponseModal(null)}
          role="presentation"
        >
          <div
            className="logs-tab-modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-labelledby="logs-tab-claw-response-title"
          >
            <div className="logs-tab-modal-header">
              <div className="logs-tab-modal-heading">
                <h3 id="logs-tab-claw-response-title">ClawCode response</h3>
                {clawResponseModal.traceShort ? (
                  <span className="logs-tab-modal-trace">Trace: {clawResponseModal.traceShort}</span>
                ) : null}
              </div>
              <button
                type="button"
                className="logs-tab-modal-close"
                onClick={() => setClawResponseModal(null)}
                aria-label="Close"
              >
                ×
              </button>
            </div>
            <div className="logs-tab-modal-body">
              {clawResponseModal.contentTruncated ? (
                <p className="logs-tab-modal-note">
                  This trace stored a shortened assistant message; the text below is everything saved for this log.
                </p>
              ) : null}
              <pre className="logs-tab-modal-pre">{clawResponseModal.text}</pre>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default LogsTab;


