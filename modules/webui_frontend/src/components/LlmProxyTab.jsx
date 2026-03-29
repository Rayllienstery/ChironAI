import React, { useState } from 'react';
import ModelSettings from './ModelSettings';
import LlmProxyWebInteractionPanel from './LlmProxyWebInteractionPanel';
import './SettingsTab.css';
import './LlmProxyTab.css';

const SUB_TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'web-interaction', label: 'Web Interaction' },
];

function LlmProxyTab({ onOpenRagModels }) {
  const [subTab, setSubTab] = useState('overview');

  return (
    <div className="settings-tab llm-proxy-tab">
      <div className="llm-proxy-header">
        <h2>LLM Proxy</h2>
        <div className="llm-proxy-subtabs" role="tablist" aria-label="LLM Proxy sections">
          {SUB_TABS.map((tab) => (
            <button
              key={tab.id}
              type="button"
              className={`llm-proxy-subtab ${subTab === tab.id ? 'llm-proxy-subtab-active' : ''}`}
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
          <div className="settings-section">
            <h3>How to use the proxy</h3>
            <p className="settings-intro">
              This is an OpenAI-compatible RAG proxy backed by Ollama and Qdrant. Point your editor or tools to the
              proxy base URL and use the <code>rag-ollama</code> model for completions with context.
            </p>
            <ul className="settings-instructions">
              <li>
                <strong>Base URL</strong>: <code>http://localhost:&lt;port&gt;</code> on the machine where this proxy runs
                (or <code>http://&lt;PC_IP&gt;:&lt;port&gt;</code> from another device). The port comes from the server
                configuration.
              </li>
              <li>
                <strong>Zed</strong>: in AI settings choose <em>OpenAI API Compatible</em>, set the API URL to the base
                URL above, and select the <code>rag-ollama</code> model. API key can be left empty unless you add your own
                authentication.
              </li>
              <li>
                <strong>VSCode + Continue.dev</strong>: configure an OpenAI-compatible provider, set the base URL to this
                proxy, and use the <code>rag-ollama</code> model.
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
                <strong>Parse request</strong>: <code>POST /v1/chat/completions</code> (OpenAI-compatible JSON). Read{' '}
                <code>messages</code>, <code>model</code> (e.g. <code>rag-ollama</code> maps to your configured Ollama
                model), <code>stream</code>, optional <code>force_rag</code>, <code>include_rag_metadata</code>, tools,
                reasoning hints. Entry: Flask blueprint from <code>llm_proxy</code> (<code>CoreModules/LlmProxy</code>).
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
                optional RAG trace when requested. The <strong>Proxy Trace</strong> tab shows per-request timings; this
                section describes the static algorithm they reflect.
              </li>
            </ol>
          </details>

          <div className="settings-section">
            <h3>Model Settings</h3>
            <ModelSettings onOpenRagModels={onOpenRagModels} />
          </div>
        </div>
      )}

      {subTab === 'web-interaction' && <LlmProxyWebInteractionPanel />}
    </div>
  );
}

export default LlmProxyTab;
