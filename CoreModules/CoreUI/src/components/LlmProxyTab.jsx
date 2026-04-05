import React, { useCallback, useEffect, useMemo, useState } from 'react';
import ModelSettings from './ModelSettings';
import LlmProxyAutocompletePanel from './LlmProxyAutocompletePanel';
import LlmProxyWebInteractionPanel from './LlmProxyWebInteractionPanel';
import ProxyTraceTab from './ProxyTraceTab';
import { getLlmProxyStatus } from '../services/api';
import '../styles/components/SettingsTab.css';
import '../styles/components/DashboardTab.css';
import '../styles/components/CoreUIPillTabs.css';
import '../styles/components/LlmProxyTab.css';

function kvRow(label, value, key) {
  return (
    <div className="dashboard-kv-row" key={key}>
      <span className="dashboard-kv-label">{label}</span>
      <span className="dashboard-kv-value">{value}</span>
    </div>
  );
}

const SUB_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'proxy-trace', label: 'Proxy Trace' },
  { id: 'autocomplete', label: 'Autocomplete' },
  { id: 'web-interaction', label: 'Web Interaction' },
];

function LlmProxyTab({ onOpenRagModels, onNavigateToRag, onOpenLogs, onModelStatusChange }) {
  const [subTab, setSubTab] = useState('overview');
  const [proxyStatus, setProxyStatus] = useState(null);
  const [statusErr, setStatusErr] = useState(null);
  const [statusBusy, setStatusBusy] = useState(false);

  const refreshStatus = useCallback(async () => {
    setStatusErr(null);
    setStatusBusy(true);
    try {
      const s = await getLlmProxyStatus();
      setProxyStatus(s);
    } catch (e) {
      setProxyStatus(null);
      setStatusErr(String(e.message || e));
    } finally {
      setStatusBusy(false);
    }
  }, []);

  useEffect(() => {
    refreshStatus();
  }, [refreshStatus]);

  const proxyInfrastructure = useMemo(() => {
    if (!proxyStatus) return null;
    return {
      docker: proxyStatus.docker,
      qdrant: proxyStatus.qdrant,
      infrastructure_error: proxyStatus.infrastructure_error,
    };
  }, [proxyStatus]);

  return (
    <div className="settings-tab llm-proxy-tab">
      <div className="llm-proxy-header">
        <div className="llm-proxy-header-row">
          <h2>LLM Proxy</h2>
          {typeof onOpenLogs === 'function' && (
            <button
              type="button"
              className="llm-proxy-open-logs-btn"
              onClick={onOpenLogs}
              aria-label="Open Logs tab to view proxy and autocomplete request history"
            >
              <svg
                className="llm-proxy-open-logs-icon"
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="currentColor"
                aria-hidden
              >
                <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z" />
              </svg>
              <span className="llm-proxy-open-logs-label">View Logs</span>
              <span className="llm-proxy-open-logs-chevron" aria-hidden>
                →
              </span>
            </button>
          )}
        </div>
        <div className="coreui-pill-tablist" role="tablist" aria-label="LLM Proxy sections">
          {SUB_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`coreui-pill-tab ${subTab === tab.id ? 'coreui-pill-tab-active' : ''}`}
              role="tab"
              aria-selected={subTab === tab.id}
              onClick={() => setSubTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {subTab === 'overview' && (
        <div className="settings-form">
          <section className="app-default-card llm-proxy-status-card" aria-labelledby="llm-proxy-status-heading">
            <div className="dashboard-card-header">
              <h2 id="llm-proxy-status-heading">Status</h2>
              <div className="dashboard-card-actions">
                <button type="button" className="dashboard-primary-btn" onClick={refreshStatus} disabled={statusBusy}>
                  Refresh
                </button>
              </div>
            </div>
            {!proxyStatus && !statusErr && <p className="dashboard-card-muted">Loading…</p>}
            {statusErr && <div className="dashboard-card-error">{statusErr}</div>}
            {proxyStatus && (
              <>
                {proxyStatus.infrastructure_error && (
                  <div className="dashboard-card-error" role="alert">
                    Could not load Docker/Qdrant status: {proxyStatus.infrastructure_error}
                  </div>
                )}
                {kvRow('Enabled', String(proxyStatus.enabled), 'enabled')}
                {kvRow('Base URL', <code>{proxyStatus.base_url}</code>, 'base')}
                {kvRow('Logical model id', <code>{proxyStatus.logical_model_id}</code>, 'logical')}
                {kvRow(
                  'Default Ollama model',
                  <code>{proxyStatus.default_ollama_model || 'unknown'}</code>,
                  'ollama',
                )}
                {kvRow(
                  'RAG collection',
                  <code>
                    {proxyStatus.rag_collection ||
                      proxyStatus.config_default_rag_collection ||
                      '—'}
                  </code>,
                  'ragcoll',
                )}
                {kvRow('Health', <code>{proxyStatus.health}</code>, 'health')}
                {proxyStatus.docker && (
                  <>
                    {kvRow(
                      'Docker CLI',
                      proxyStatus.docker.cli_available ? 'available' : 'not found',
                      'dock-cli',
                    )}
                    {kvRow(
                      'Docker Engine',
                      proxyStatus.docker.engine_available ? 'running' : 'not running',
                      'dock-eng',
                    )}
                  </>
                )}
                {proxyStatus.qdrant && (
                  <>
                    {kvRow(
                      'Qdrant HTTP',
                      proxyStatus.qdrant.reachable ? 'reachable' : 'unreachable',
                      'q-http',
                    )}
                    {kvRow(
                      'Qdrant container',
                      proxyStatus.qdrant.container_running ? 'running' : 'not running',
                      'q-ct',
                    )}
                  </>
                )}
              </>
            )}
          </section>

          <div className="settings-section">
            <h3>How to use the proxy</h3>
            <p className="settings-intro">
              This RAG proxy speaks <strong>OpenAI</strong> (<code>POST /v1/chat/completions</code>) and{' '}
              <strong>Anthropic Messages</strong> (<code>POST /v1/messages</code>) over the same base URL, backed by Ollama
              and Qdrant. Use the <code>ChironAI-Worker</code> model for chat with context. Optional inline completions
              use logical id <code>ChironAI-Autocomplete</code> — configure it on the <strong>Autocomplete</strong> tab.
            </p>
            <ul className="settings-instructions">
              <li>
                <strong>Base URL</strong>: <code>http://localhost:&lt;port&gt;</code> on the machine where this proxy runs
                (or <code>http://&lt;PC_IP&gt;:&lt;port&gt;</code> from another device). The port comes from the server
                configuration.
              </li>
              <li>
                <strong>Zed</strong>: in AI settings choose <em>OpenAI API Compatible</em>, set the API URL to the base
                URL above. Use <code>ChironAI-Worker</code> for assistant chat; for inline completions use{' '}
                <code>ChironAI-Autocomplete</code> after you configure it (see the <strong>Autocomplete</strong> tab).
                API key can be left empty unless you add your own authentication.
              </li>
              <li>
                <strong>VSCode + Continue.dev</strong>: configure an OpenAI-compatible provider, set the base URL to this
                proxy, and use the <code>ChironAI-Worker</code> model.
              </li>
              <li>
                <strong>Claude Code (Anthropic)</strong>: set <code>ANTHROPIC_BASE_URL</code> to this proxy&apos;s base URL
                (no path suffix), <code>ANTHROPIC_API_KEY</code> empty, <code>ANTHROPIC_AUTH_TOKEN=ollama</code> (or your
                token policy). Run <code>claude --model ChironAI-Worker</code> (or your Ollama tag). List models with
                header <code>anthropic-version: 2023-06-01</code> on <code>GET /v1/models</code>. See{' '}
                <code>CoreModules/LlmProxy/README.md</code>.
              </li>
              <li>
                The model and RAG behavior for the proxy are controlled by the settings below. Web and GitHub options
                live under the <strong>Web Interaction</strong> tab.
              </li>
            </ul>
          </div>

          <details className="settings-section pipeline-details">
            <summary>
              <strong>Request pipeline (algorithm)</strong>
              <span className="settings-hint"> — end-to-end path from HTTP body to response</span>
            </summary>
            <ol className="pipeline-steps">
              <li>
                <strong>Parse request</strong>: <code>POST /v1/chat/completions</code> (OpenAI) or{' '}
                <code>POST /v1/messages</code> (Anthropic → same internal pipeline). Read <code>messages</code> /{' '}
                <code>model</code> (e.g. <code>ChironAI-Worker</code> maps to your configured Ollama model),{' '}
                <code>stream</code>, optional <code>force_rag</code>, <code>include_rag_metadata</code>, tools, reasoning
                hints. Entry: Flask blueprint from <code>llm_proxy</code> (<code>CoreModules/LlmProxy</code>).
              </li>
              <li>
                <strong>Resolve last user message</strong>: the last user turn is the question for RAG and for the final
                chat. System/developer/tool messages are preserved for context.
              </li>
              <li>
                <strong>RAG gate</strong>: compute a trigger score (keywords, code blocks, technical terms). Skip vector
                search for very short greetings or when required-keyword policy says so (unless{' '}
                <code>force_rag</code>). Implemented in <code>domain.services.rag_trigger</code> /{' '}
                <code>build_rag_context</code>.
              </li>
              <li>
                <strong>Retrieval</strong> (<code>application.rag.use_cases.search_rag</code>): normalize the question with{' '}
                <code>query_for_retrieval</code> (strip code fences, stop words, framework hints, optional API-symbol
                expansion). Optionally run <strong>query expansion</strong> (config: extra paraphrases, merged with RRF).
                Embed the query string(s), then search Qdrant: <strong>dense</strong> vector always; if the collection has
                sparse vectors and <strong>hybrid sparse</strong> is enabled (RAG / Qdrant → Models for RAG / Qdrant), add a{' '}
                <strong>keyword sparse</strong> vector and use hybrid fusion (RRF). That same toggle controls sparse vectors
                when <strong>creating new collections</strong>. Metadata filters (<code>doc_type</code> / <code>doc_scope</code>)
                may apply; empty results retry without filter. Version-focused questions add extra version-tuned searches before merge.
              </li>
              <li>
                <strong>Rank</strong>: sort by document-type/scope priority, then optional <strong>LLM rerank</strong>{' '}
                on a candidate subset when rerank is enabled.
              </li>
              <li>
                <strong>Build context</strong>: <code>framework_filter</code> + <code>build_context_block</code> turn hits
                into a single context string with citations metadata for the UI trace.
              </li>
              <li>
                <strong>Web supplement (optional, free)</strong>: if enabled in <strong>Web Interaction</strong>, DuckDuckGo
                text snippets may be appended after the RAG block in the system message for freshness (releases, versions).
                Separately, <strong>Fetch Web knowledge</strong> enables merged multi-collection retrieval and background
                GitHub markdown refresh via <code>external_docs_rag</code> (public GitHub API, rate-limited).
              </li>
              <li>
                <strong>Prompt assembly</strong>: <code>prepare_ollama_messages</code> /{' '}
                <code>build_system_content</code> prepend system instructions (prefix/suffix from config), inject RAG
                context and optional web snippet block, then append the user/assistant/tool conversation for the downstream model.
              </li>
              <li>
                <strong>LLM call</strong>: send messages to Ollama (<code>/api/chat</code>). Non-streaming returns one JSON
                completion; streaming yields SSE chunks in OpenAI shape.
              </li>
              <li>
                <strong>Response</strong>: JSON (or stream) with assistant content, model id, usage approximations, and
                optional RAG trace when requested. The <strong>Proxy Trace</strong> sub-tab shows per-request timings;
                this section describes the static algorithm they reflect.
              </li>
            </ol>
          </details>

          <div className="settings-section">
            <h3>Model Settings</h3>
            <ModelSettings
              onOpenRagModels={onOpenRagModels}
              onNavigateToRag={onNavigateToRag}
              onModelStatusChange={onModelStatusChange}
              proxyInfrastructure={proxyInfrastructure}
            />
          </div>
        </div>
      )}

      {subTab === 'proxy-trace' && <ProxyTraceTab />}

      {subTab === 'autocomplete' && <LlmProxyAutocompletePanel />}

      {subTab === 'web-interaction' && <LlmProxyWebInteractionPanel />}
    </div>
  );
}

export default LlmProxyTab;
