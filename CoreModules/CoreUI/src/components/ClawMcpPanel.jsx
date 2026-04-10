import React, { useCallback, useEffect, useState } from 'react';
import { getClawCodeStatus } from '../services/api';
import '../styles/components/DashboardTab.css';

function ClawMcpPanel() {
  const [status, setStatus] = useState(null);
  const [err, setErr] = useState(null);

  const refresh = useCallback(async () => {
    setErr(null);
    try {
      const s = await getClawCodeStatus();
      setStatus(s);
    } catch (e) {
      setStatus({ available: false, reason: e.message || 'request failed' });
      setErr(String(e.message || e));
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  if (!status) {
    return (
      <div className="dashboard-layout">
        <section className="app-default-card" aria-labelledby="claw-mcp-loading-heading">
          <div className="dashboard-card-header">
            <h2 id="claw-mcp-loading-heading">MCP</h2>
          </div>
          <p className="dashboard-card-muted">Loading…</p>
        </section>
      </div>
    );
  }

  if (!status.available) {
    return (
      <div className="dashboard-layout">
        <section className="app-default-card" aria-labelledby="claw-mcp-unavailable-heading">
          <div className="dashboard-card-header">
            <h2 id="claw-mcp-unavailable-heading">MCP</h2>
          </div>
          <p className="dashboard-card-muted">
            ClawCode unavailable ({status.reason || 'unknown'}).
            {err && <span className="dashboard-card-error"> {err}</span>}
          </p>
        </section>
      </div>
    );
  }

  return (
    <div className="dashboard-layout">
      <div className="dashboard-claw-two-col">
        <div className="dashboard-claw-col">
          <section className="app-default-card" aria-labelledby="claw-mcp-overview-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-mcp-overview-heading">MCP overview</h2>
            </div>
            <p className="dashboard-card-muted">
              <strong>MCP</strong> (Model Context Protocol) lets an IDE attach <em>tools</em> and <em>resources</em> to an
              AI session — often via <strong>stdio</strong> (a subprocess). ChironAI exposes a small{' '}
              <strong>HTTP info</strong> service on port <code>{status.mcp_port}</code> for health and orientation; it
              is <em>not</em> a full MCP JSON-RPC server.
            </p>
            <p className="dashboard-card-muted">
              MCP HTTP enabled: <strong>{String(status.mcp_http_enabled)}</strong>
            </p>
          </section>
        </div>
        <div className="dashboard-claw-col">
          <section className="app-default-card" aria-labelledby="claw-mcp-usage-heading">
            <div className="dashboard-card-header">
              <h2 id="claw-mcp-usage-heading">Usage and links</h2>
              <div className="dashboard-card-actions">
                <button type="button" className="dashboard-primary-btn" onClick={refresh}>
                  Refresh status
                </button>
              </div>
            </div>
            <ul className="dashboard-card-muted" style={{ margin: '0 0 var(--md-sys-spacing-md) 1.25rem', padding: 0 }}>
              <li style={{ marginBottom: 'var(--md-sys-spacing-sm)' }}>
                <strong>Chat / agent with custom base URL</strong> → <strong>Claw Proxy</strong> on port{' '}
                <code>8082</code>: OpenAI base URL for <code>/v1/chat/completions</code>, or set Claude Code{' '}
                <code>ANTHROPIC_BASE_URL</code> to the same host for <code>/v1/messages</code>. Set{' '}
                <code>model</code> to an Ollama tag from <code>GET /v1/models</code> on that port (or use an LLM Proxy
                build with <code>backend: claw</code>).
              </li>
              <li style={{ marginBottom: 'var(--md-sys-spacing-sm)' }}>
                <strong>VS Code MCP servers</strong> → configure per Microsoft / extension docs (stdio command). See{' '}
                <code>docs/CLAWCODE_VSCODE.md</code>.
              </li>
              <li>
                <strong>Info endpoint</strong>:{' '}
                <a href={status.mcp_info_url} target="_blank" rel="noreferrer">
                  {status.mcp_info_url}
                </a>{' '}
                (only if <code>mcp_http_enabled</code> and the server was started).
              </li>
            </ul>
          </section>
        </div>
      </div>
    </div>
  );
}

export default ClawMcpPanel;
