import { useCallback, useEffect, useState } from 'react';
import LlmProxyWebInteractionPanel from './LlmProxyWebInteractionPanel';
import CoreUIButton from './CoreUIButton';
import CoreUIPipelinePreview from './CoreUIPipelinePreview';

import { getLlmProxyStatus } from '../services/api';

import '../styles/components/SettingsTab.css';
import '../styles/components/DashboardTab.css';
import '../styles/components/LlmProxyTab.css';
import CoreUIPillTabs from './CoreUIPillTabs';

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
  { id: 'web-interaction', label: 'Web Interaction' },
];

const PIPELINE_STEPS = [
  {
    id: 'parse',
    label: 'Parse request',
    description: 'POST /v1/chat/completions (OpenAI) or POST /v1/messages (Anthropic). Read messages, model (build id), stream, tools, and reasoning hints.',
    icon: 'login',
    active: true,
    tone: 'success'
  },
  {
    id: 'resolve',
    label: 'Resolve last user message',
    description: 'The last user turn is the question for RAG and for the final chat. System/developer/tool messages are preserved for context.',
    icon: 'person',
    active: true,
    tone: 'success'
  },
  {
    id: 'gate',
    label: 'RAG gate',
    description: 'Compute trigger score (keywords, code blocks, technical terms). Skip vector search for short greetings or when policy requires.',
    icon: 'gate',
    active: true,
    tone: 'success'
  },
  {
    id: 'retrieval',
    label: 'Retrieval',
    description: 'Normalize question, query expansion, embed, and search Qdrant (dense/sparse/hybrid). Metadata filters and version-tuned searches apply.',
    icon: 'database',
    active: true,
    tone: 'success',
    badges: ['Qdrant', 'Hybrid']
  },
  {
    id: 'rank',
    label: 'Rank',
    description: 'Sort by document-type/scope priority, then optional LLM rerank on a candidate subset when enabled.',
    icon: 'swap_vert',
    active: true,
    tone: 'success',
    badges: ['Rerank']
  },
  {
    id: 'context',
    label: 'Build context',
    description: 'framework_filter + build_context_block turn hits into a single context string with citations metadata for the UI trace.',
    icon: 'build',
    active: true,
    tone: 'success'
  },
  {
    id: 'web',
    label: 'Web supplement',
    description: 'Optional DuckDuckGo snippets or Fetch Web knowledge (GitHub markdown refresh) for freshness.',
    icon: 'public',
    active: true,
    tone: 'info',
    badges: ['DuckDuckGo', 'GitHub']
  },
  {
    id: 'assembly',
    label: 'Prompt assembly',
    description: 'Prepend system instructions, inject RAG context and optional web snippet block, then append the conversation.',
    icon: 'psychology',
    active: true,
    tone: 'success'
  },
  {
    id: 'llm',
    label: 'LLM call',
    description: 'Send messages through the provider runtime. Non-streaming returns JSON; streaming yields SSE chunks in OpenAI shape.',
    icon: 'smart_toy',
    active: true,
    tone: 'success'
  },
  {
    id: 'response',
    label: 'Response',
    description: 'JSON or stream with assistant content, model id, usage approximations, and optional RAG trace.',
    icon: 'output',
    active: true,
    tone: 'success'
  }
];

function LlmProxyTab({ onOpenLogs }) {

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

  return (
    <div className="settings-tab settings-tab--fullwidth llm-proxy-tab tab-view">
      <div className="llm-proxy-header">
        <div className="llm-proxy-header-row">
          <h2>RAG Fusion Proxy</h2>
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
        <CoreUIPillTabs
          tabs={SUB_TABS}
          value={subTab}
          onChange={setSubTab}
          ariaLabel="RAG Fusion Proxy sections"
        />
      </div>

      {subTab === 'overview' && (
        <div className="settings-form">
          <section className="app-default-card llm-proxy-status-card" aria-labelledby="llm-proxy-status-heading">
            <div className="dashboard-card-header">
              <h2 id="llm-proxy-status-heading">Status</h2>
              <div className="dashboard-card-actions">
                <CoreUIButton variant="primary" onClick={refreshStatus} disabled={statusBusy}>
                  Refresh
                </CoreUIButton>
              </div>
            </div>
            {!proxyStatus && !statusErr && <p className="dashboard-card-muted">Loading…</p>}
            {statusErr && <div className="dashboard-card-error">{statusErr}</div>}
            {proxyStatus && (
              <>
                {kvRow('Enabled', String(proxyStatus.enabled), 'enabled')}
                {kvRow('Base URL', <code>{proxyStatus.base_url}</code>, 'base')}
                {kvRow('Health', <code>{proxyStatus.health}</code>, 'health')}
              </>
            )}
          </section>

          <details className="settings-section pipeline-details" open>
            <summary>
              <strong>Request pipeline (algorithm)</strong>
              <span className="settings-hint"> — end-to-end path from HTTP body to response</span>
            </summary>
            <div className="llm-proxy-pipeline-wrap">
              <CoreUIPipelinePreview steps={PIPELINE_STEPS} animated />
            </div>
          </details>



        </div>
      )}

      {subTab === 'web-interaction' && <LlmProxyWebInteractionPanel />}
    </div>
  );
}

export default LlmProxyTab;
