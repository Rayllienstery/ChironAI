import React, { useCallback, useEffect, useState } from 'react';
import { getOpenclawStatus } from '../services/api';
import './SettingsTab.css';

function ClawMcpTab() {
  const [status, setStatus] = useState(null);

  const refresh = useCallback(async () => {
    try {
      const s = await getOpenclawStatus();
      setStatus(s);
    } catch {
      setStatus({ available: false, reason: 'request failed' });
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!status) {
    return (
      <div className="settings-tab">
        <p className="settings-intro">Loading…</p>
      </div>
    );
  }

  if (!status.available) {
    return (
      <div className="settings-tab">
        <h2>Claw MCP</h2>
        <p className="settings-intro">OpenClaw unavailable ({status.reason || 'unknown'}).</p>
      </div>
    );
  }

  return (
    <div className="settings-tab">
      <h2>Claw MCP</h2>
      <p className="settings-intro">
        <strong>MCP</strong> (Model Context Protocol) lets an IDE attach <em>tools</em> and <em>resources</em> to an AI
        session over a standard wire — often <strong>stdio</strong> (a subprocess). ChironAI exposes a small{' '}
        <strong>HTTP info</strong> service on port <code>{status.mcp_port}</code> (default 8083) for health and
        orientation; it is <em>not</em> a full MCP JSON-RPC server.
      </p>
      <div className="settings-section">
        <h3>When to use what</h3>
        <ul className="settings-instructions">
          <li>
            <strong>Chat / agent with custom base URL</strong> → use <strong>Claw OpenAI</strong> base URL (port 8082),{' '}
            model <code>{status.logical_model_id}</code>.
          </li>
          <li>
            <strong>VS Code MCP servers</strong> → configure per Microsoft / extension docs (stdio command). See{' '}
            <code>docs/OPENCLAW_VSCODE.md</code>.
          </li>
          <li>
            <strong>Info endpoint</strong>:{' '}
            <a href={status.mcp_info_url} target="_blank" rel="noreferrer">
              {status.mcp_info_url}
            </a>{' '}
            (only if <code>mcp_http_enabled</code> and the server was started).
          </li>
        </ul>
        <p className="settings-hint">
          MCP HTTP enabled: <strong>{String(status.mcp_http_enabled)}</strong>
        </p>
        <button type="button" className="save-button" onClick={refresh}>
          Refresh status
        </button>
      </div>
    </div>
  );
}

export default ClawMcpTab;
