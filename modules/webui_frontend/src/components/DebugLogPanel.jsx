import React, { useState, useEffect, useRef } from 'react';
import { getLogs } from '../services/api';
import { startLogPolling, stopLogPolling } from '../services/logs';
import './DebugLogPanel.css';

function DebugLogPanel({ open, onToggle, sessionId }) {
  const [logs, setLogs] = useState([]);
  const [levelFilter, setLevelFilter] = useState('');
  const [sourceFilter, setSourceFilter] = useState('');
  const logsEndRef = useRef(null);
  const panelRef = useRef(null);

  useEffect(() => {
    if (!sessionId || !open) {
      stopLogPolling();
      return;
    }

    loadLogs();

    // Start auto-update polling
    startLogPolling(sessionId, (newLogs) => {
      setLogs(prev => {
        const existingIds = new Set(prev.map(log => log.id));
        const uniqueNewLogs = newLogs.filter(log => !existingIds.has(log.id));
        return [...prev, ...uniqueNewLogs].slice(-200); // Keep last 200
      });
      scrollToBottom();
    }, 2000);

    return () => {
      stopLogPolling();
    };
  }, [sessionId, open, levelFilter]);

  const loadLogs = async () => {
    if (!sessionId) return;
    
    try {
      const data = await getLogs(sessionId, {
        level: levelFilter || undefined,
        source: sourceFilter || undefined,
        limit: 100,
      });
      setLogs(data.logs || []);
      scrollToBottom();
    } catch (error) {
      console.error('Failed to load logs:', error);
    }
  };

  const scrollToBottom = () => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

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
      return new Date(timestamp).toLocaleTimeString();
    } catch {
      return timestamp;
    }
  };

  if (!sessionId) {
    return null;
  }

  return (
    <>
      <button
        className="debug-log-toggle"
        onClick={onToggle}
        aria-label={open ? 'Hide Debug Log' : 'Show Debug Log'}
      >
        {open ? '▼' : '▲'} Debug Log
      </button>
      
      <div
        ref={panelRef}
        className={`debug-log-panel ${open ? 'open' : ''}`}
      >
        <div className="debug-log-header">
          <span>Debug Log</span>
          <div className="debug-log-controls">
            <select
              value={levelFilter}
              onChange={(e) => setLevelFilter(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            >
              <option value="">All</option>
              <option value="ERROR">ERROR</option>
              <option value="WARNING">WARNING</option>
              <option value="INFO">INFO</option>
            </select>
            <select
              value={sourceFilter}
              onChange={(e) => setSourceFilter(e.target.value)}
              onClick={(e) => e.stopPropagation()}
            >
              <option value="">All sources</option>
              <option value="ollama">Ollama</option>
              <option value="rag_routes.chat_completions">rag_routes</option>
              <option value="webui_routes">webui_routes</option>
            </select>
            <button onClick={loadLogs}>Refresh</button>
          </div>
        </div>
        
        <div className="debug-log-content">
          {logs.length === 0 ? (
            <div className="empty-state">No logs</div>
          ) : (
            logs.map((log) => (
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
            ))
          )}
          <div ref={logsEndRef} />
        </div>
      </div>
    </>
  );
}

export default DebugLogPanel;

