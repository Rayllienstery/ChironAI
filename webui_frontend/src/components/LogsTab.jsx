import React, { useState, useEffect, useRef } from 'react';
import { getLogs } from '../services/api';
import { startLogPolling, stopLogPolling } from '../services/logs';
import './LogsTab.css';

function LogsTab({ sessionId }) {
  const [logs, setLogs] = useState([]);
  const [levelFilter, setLevelFilter] = useState('');
  const [loading, setLoading] = useState(true);
  const logsEndRef = useRef(null);

  useEffect(() => {
    if (!sessionId) return;

    loadLogs();

    // Start auto-update polling
    startLogPolling(sessionId, (newLogs) => {
      setLogs(prev => {
        const existingIds = new Set(prev.map(log => log.id));
        const uniqueNewLogs = newLogs.filter(log => !existingIds.has(log.id));
        return [...prev, ...uniqueNewLogs].slice(-500); // Keep last 500
      });
      scrollToBottom();
    }, 3000);

    return () => {
      stopLogPolling();
    };
  }, [sessionId, levelFilter]);

  const loadLogs = async () => {
    if (!sessionId) return;
    
    setLoading(true);
    try {
      const data = await getLogs(sessionId, {
        level: levelFilter || undefined,
        limit: 100,
      });
      setLogs(data.logs || []);
      scrollToBottom();
    } catch (error) {
      console.error('Failed to load logs:', error);
    } finally {
      setLoading(false);
    }
  };

  const scrollToBottom = () => {
    logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const getLevelClass = (level) => {
    return `log-entry log-${level.toLowerCase()}`;
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return 'N/A';
    try {
      return new Date(timestamp).toLocaleString();
    } catch {
      return timestamp;
    }
  };

  if (!sessionId) {
    return <div className="loading">No session available</div>;
  }

  return (
    <div className="logs-tab">
      <div className="logs-header">
        <h2>Logs</h2>
        <div className="logs-controls">
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
          >
            <option value="">All Levels</option>
            <option value="ERROR">ERROR</option>
            <option value="WARNING">WARNING</option>
            <option value="INFO">INFO</option>
          </select>
          <button onClick={loadLogs}>Refresh</button>
        </div>
      </div>

      <div className="logs-content">
        {loading && logs.length === 0 ? (
          <div className="loading">Loading logs...</div>
        ) : logs.length === 0 ? (
          <div className="empty-state">No logs found</div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className={getLevelClass(log.level)}>
              <div className="log-header">
                <span className="log-level">[{log.level}]</span>
                <span className="log-timestamp">{formatTimestamp(log.timestamp)}</span>
              </div>
              {log.source && (
                <div className="log-source">Source: {log.source}</div>
              )}
              {log.error_type && (
                <div className="log-error-type">Type: {log.error_type}</div>
              )}
              <div className="log-message">{log.message}</div>
            </div>
          ))
        )}
        <div ref={logsEndRef} />
      </div>
    </div>
  );
}

export default LogsTab;

