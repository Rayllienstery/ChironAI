import React, { useEffect, useState, useCallback } from 'react';
import PipelineCiDiagram from './PipelineCiDiagram';
import { useMergedPipelinePreview } from '../hooks/useMergedPipelinePreview';
import { getLlmProxyBuilds, getModelSettings, getRagStatus } from '../services/api';
import '../styles/components/DashboardTab.css';

const INFO_TABS = [
  { id: 'intro', label: 'Intro' },
  { id: 'features', label: 'Features' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'quick-start', label: 'Quick Start' },
  { id: 'credits', label: 'Credits' },
];

const PROXY_GUIDE_TABS = [
  { id: 'why', label: 'Why' },
  { id: 'claude', label: 'Claude Code' },
  { id: 'codex', label: 'Codex' },
  { id: 'configured', label: 'Configured' },
  { id: 'checks', label: 'Checks' },
];

const PROXY_CUSTOM_PRESETS = [
  {
    id: 'local-default',
    label: 'Local default (8080)',
    baseUrl: 'http://127.0.0.1:8080',
    buildId: 'your-build-id',
    authToken: 'ollama',
    openAiApiKey: 'ollama',
  },
  {
    id: 'lan-machine',
    label: 'Remote LAN machine',
    baseUrl: 'http://192.168.1.10:8080',
    buildId: 'team-shared-build',
    authToken: 'ollama',
    openAiApiKey: 'ollama',
  },
  {
    id: 'custom-token',
    label: 'Custom auth token',
    baseUrl: 'http://127.0.0.1:8080',
    buildId: 'secure-build-id',
    authToken: 'your-token',
    openAiApiKey: 'your-token',
  },
];

function formatBool(v) {
  return v ? 'On' : 'Off';
}

function DashboardLlmProxyCard({ onNavigate, onOpenLogs, onOpenLlmProxyAutocomplete }) {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [settings, setSettings] = useState(null);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const data = await getModelSettings();
      setSettings(data || {});
    } catch (e) {
      console.error(e);
      setLoadError(e.message || 'Failed to load');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const row = (label, value, titleAttr) => (
    <div className="dashboard-kv-row" key={label}>
      <span className="dashboard-kv-label">{label}</span>
      <span className="dashboard-kv-value" title={titleAttr || (typeof value === 'string' ? value : undefined)}>
        {value === '' || value == null ? '—' : String(value)}
      </span>
    </div>
  );

  return (
    <section className="app-default-card dashboard-proxy-card" aria-labelledby="dashboard-proxy-heading">
      <div className="dashboard-card-header">
        <h2 id="dashboard-proxy-heading">RAG Fusion Proxy</h2>
        <div className="dashboard-card-actions">
          {typeof onOpenLogs === 'function' && (
            <button type="button" className="dashboard-text-btn" onClick={() => onOpenLogs()}>
              View Logs
            </button>
          )}
          <button type="button" className="dashboard-primary-btn" onClick={() => onNavigate('rag-fusion-proxy')}>
            Open RAG Fusion Proxy
          </button>
        </div>
      </div>
      {loading && <div className="dashboard-card-muted">Loading…</div>}
      {loadError && (
        <div className="dashboard-card-error">
          {loadError}
          <button type="button" className="dashboard-text-btn" onClick={load}>
            Retry
          </button>
        </div>
      )}
      {!loading && !loadError && settings && (
        <div className="dashboard-proxy-sections">
          <div className="dashboard-proxy-block">
            <h3 className="dashboard-proxy-block-title">Chat / RAG</h3>
            {row('Model', settings.model)}
            {row('Prompt', settings.prompt_name)}
            {row('RAG collection', settings.rag_collection)}
            {row('Temperature', settings.temperature)}
            {row('Top P', settings.top_p)}
            {row('Code only', formatBool(settings.code_only))}
            {row('Include RAG metadata', formatBool(settings.include_rag_metadata))}
            {row('Rerank for RAG', formatBool(settings.rerank_for_rag))}
            {row('Rerank model', settings.rerank_model)}
          </div>
          <div className="dashboard-proxy-block">
            <div className="dashboard-proxy-block-title-row">
              <h3 className="dashboard-proxy-block-title">Autocomplete</h3>
              {typeof onOpenLlmProxyAutocomplete === 'function' && (
                <button type="button" className="dashboard-text-btn" onClick={() => onOpenLlmProxyAutocomplete()}>
                  Configure in LLM Proxy
                </button>
              )}
            </div>
            {row('Autocomplete model', settings.autocomplete_model)}
          </div>
          <div className="dashboard-proxy-block">
            <h3 className="dashboard-proxy-block-title">Web</h3>
            {row('Fetch web knowledge', formatBool(settings.fetch_web_knowledge))}
            {row('Web interaction', formatBool(settings.web_interaction_enabled))}
            {row('On keywords', formatBool(settings.web_interaction_on_keywords))}
            {row('On low confidence (framework)', formatBool(settings.web_interaction_on_low_confidence_framework))}
            {row('DDG news', formatBool(settings.web_interaction_ddg_news))}
            {row('Fetch page', formatBool(settings.web_interaction_fetch_page))}
            {row('Wikipedia', formatBool(settings.web_interaction_wikipedia))}
          </div>
        </div>
      )}
    </section>
  );
}

function DashboardRagCard({ onNavigate }) {
  const { merged: pipelineMerged, reload: reloadPipeline } = useMergedPipelinePreview();
  const [status, setStatus] = useState(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState(null);

  const loadStatus = useCallback(async () => {
    setStatusError(null);
    try {
      const s = await getRagStatus();
      setStatus(s);
    } catch (e) {
      console.error(e);
      setStatusError(e.message || 'Failed to load status');
    } finally {
      setStatusLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const refreshAll = () => {
    loadStatus();
    reloadPipeline();
  };

  return (
    <section className="app-default-card dashboard-rag-card" aria-labelledby="dashboard-rag-heading">
      <div className="dashboard-card-header">
        <h2 id="dashboard-rag-heading">RAG / Qdrant</h2>
        <div className="dashboard-card-actions">
          <button type="button" className="dashboard-secondary-btn" onClick={refreshAll}>
            Refresh
          </button>
          <button type="button" className="dashboard-primary-btn" onClick={() => onNavigate('rag')}>
            Open RAG / Qdrant
          </button>
        </div>
      </div>
      {statusLoading && <div className="dashboard-card-muted">Loading status…</div>}
      {statusError && (
        <div className="dashboard-card-error">
          {statusError}
          <button type="button" className="dashboard-text-btn" onClick={loadStatus}>
            Retry
          </button>
        </div>
      )}
      {!statusLoading && !statusError && status && (
        <div className="dashboard-rag-status-grid" role="group" aria-label="Qdrant status">
          <div className="dashboard-rag-status-pill">
            <span className="dashboard-rag-status-label">Running</span>
            <span className="dashboard-rag-status-value">{status.running ? 'Yes' : 'No'}</span>
          </div>
          <div className="dashboard-rag-status-pill dashboard-rag-status-pill--wide">
            <span className="dashboard-rag-status-label">Endpoint</span>
            <span className="dashboard-rag-status-value" title={status.url || ''}>
              {status.url || '—'}
            </span>
          </div>
          <div className="dashboard-rag-status-pill">
            <span className="dashboard-rag-status-label">Collections</span>
            <span className="dashboard-rag-status-value">
              {status.collections_count != null ? String(status.collections_count) : '—'}
            </span>
          </div>
        </div>
      )}
      <div className="dashboard-rag-pipeline-wrap">
        <PipelineCiDiagram
          data={pipelineMerged}
          title="LLM proxy pipeline (RAG + supplements)"
          subtitle="Stages enabled with current server settings. Edit details on the RAG / Qdrant tab."
          compact
        />
      </div>
    </section>
  );
}

function DashboardTab({ onNavigate, onOpenLogs, onOpenLlmProxyAutocomplete }) {
  const [infoSubTab, setInfoSubTab] = useState('intro');
  const [proxyGuideTab, setProxyGuideTab] = useState('why');
  const [proxyPresetId, setProxyPresetId] = useState(PROXY_CUSTOM_PRESETS[0].id);
  const [configuredBaseUrl, setConfiguredBaseUrl] = useState(PROXY_CUSTOM_PRESETS[0].baseUrl);
  const [configuredBuildId, setConfiguredBuildId] = useState(PROXY_CUSTOM_PRESETS[0].buildId);
  const [configuredAuthToken, setConfiguredAuthToken] = useState(PROXY_CUSTOM_PRESETS[0].authToken);
  const [configuredOpenAiApiKey, setConfiguredOpenAiApiKey] = useState(PROXY_CUSTOM_PRESETS[0].openAiApiKey);
  const [availableBuildIds, setAvailableBuildIds] = useState([]);

  const go = (tabId) => {
    if (typeof onNavigate === 'function') onNavigate(tabId);
  };

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getLlmProxyBuilds();
        if (cancelled) return;
        const ids = Array.isArray(data?.builds)
          ? data.builds
              .map((x) => String(x?.id || '').trim())
              .filter((x) => x.length > 0)
          : [];
        setAvailableBuildIds(ids);
        if (ids.length > 0) {
          setConfiguredBuildId((prev) => {
            const normalizedPrev = String(prev || '').trim();
            return ids.includes(normalizedPrev) ? prev : ids[0];
          });
        }
      } catch {
        if (!cancelled) setAvailableBuildIds([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <div className="dashboard-tab">
      <div className="dashboard-layout">
        <section className="dashboard-info-card" aria-label="About ChironAI">
          <div className="dashboard-info-card-header">
            <h2 className="dashboard-info-card-title">ChironAI</h2>
            <p className="dashboard-info-card-subtitle">Local, model-agnostic RAG layer for developers</p>
          </div>
          <div className="dashboard-info-subtabs" role="tablist" aria-label="About sections">
            {INFO_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`dashboard-info-subtab ${infoSubTab === tab.id ? 'dashboard-info-subtab-active' : ''}`}
                role="tab"
                aria-selected={infoSubTab === tab.id}
                onClick={() => setInfoSubTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="dashboard-info-panel" role="tabpanel">
            {infoSubTab === 'intro' && (
              <>
                <div className="dashboard-section-inner notice-section">
                  <div className="notice-content">
                    <h3>Modular RAG Platform</h3>
                    <p>
                      <strong>ChironAI is a modular RAG platform</strong> for local LLMs, built with a domain-agnostic architecture.
                      It is configured by default for Apple ecosystem development (iOS, macOS, Swift, SwiftUI, UIKit, Observation, etc.)
                      but supports any knowledge domain through source and prompt configuration.
                    </p>
                    <p>
                      The platform solves documentation-driven development challenges by providing accurate, up-to-date knowledge
                      through RAG, ensuring code quality and architectural compliance. Switch domains by changing indexing sources
                      and system prompts—no core changes required.
                    </p>
                  </div>
                </div>
                <div className="dashboard-section-inner">
                  <h3>What is ChironAI?</h3>
                  <p>
                    ChironAI is a local, model-agnostic RAG (Retrieval-Augmented Generation) layer designed for developers.
                    It works with any LLM (local or cloud) and provides accurate, up-to-date knowledge
                    through a modular fetcher/crawler and RAG system.
                  </p>
                  <p>
                    The system delivers predictable, engineering-focused results with strict response structure (RAG facts
                    → implementation → summary), adherence to architecture (Clean/MVVM), Swift 6 strict concurrency,
                    Observation, UI rules, and controlled variability (minimal randomness in generation).
                  </p>
                </div>
              </>
            )}
            {infoSubTab === 'features' && (
              <div className="dashboard-section-inner">
                <h3>Key Features</h3>
                <div className="features-grid">
                  <div className="feature-card">
                    <h4>Model Agnostic</h4>
                    <p>Works with any LLM (local or cloud)</p>
                  </div>
                  <div className="feature-card">
                    <h4>Smart RAG</h4>
                    <p>Hybrid search (vector + keyword), versioning (iOS/Swift), doc_type/section-aware chunking</p>
                  </div>
                  <div className="feature-card">
                    <h4>Modular Architecture</h4>
                    <p>Layered architecture: Presentation → Application → Domain → Infrastructure</p>
                  </div>
                  <div className="feature-card">
                    <h4>Predictable Results</h4>
                    <p>Strict response structure, architecture compliance, controlled variability</p>
                  </div>
                  <div className="feature-card">
                    <h4>Documentation Sources</h4>
                    <p>Apple Developer Documentation (iOS, macOS, Swift, SwiftUI, UIKit, Observation)</p>
                  </div>
                  <div className="feature-card">
                    <h4>Extensible</h4>
                    <p>Support for additional sources (MDN, blogs, GitHub Docs, etc.)</p>
                  </div>
                  <div className="feature-card">
                    <h4>Dual API Compatibility</h4>
                    <p>OpenAI /v1/chat/completions + Anthropic /v1/messages — single proxy, two formats</p>
                  </div>
                  <div className="feature-card">
                    <h4>Agent traces</h4>
                    <p>RAG Fusion proxy can record multi-step traces (tool calls, RAG, skills) for debugging in the Web UI</p>
                  </div>
                  <div className="feature-card">
                    <h4>Local-First Infrastructure</h4>
                    <p>Ollama + Qdrant + Docker — all local, auto-install and start services (ServiceStarter)</p>
                  </div>
                  <div className="feature-card">
                    <h4>Streaming Synthesis</h4>
                    <p>SSE for OpenAI and Anthropic formats — streaming even when model doesn't support it</p>
                  </div>
                  <div className="feature-card">
                    <h4>Build Presets</h4>
                    <p>Configurable builds — switch models via model parameter</p>
                  </div>
                  <div className="feature-card">
                    <h4>Autocomplete Support</h4>
                    <p>Logical model for fast inline completions — separate fast path without RAG</p>
                  </div>
                  <div className="feature-card">
                    <h4>Architecture Guards</h4>
                    <p>import-linter contracts — domain never imports infrastructure/api, boundary protection</p>
                  </div>
                  <div className="feature-card">
                    <h4>MD Ingestion Pipeline</h4>
                    <p>Config-driven markdown preprocessing: filtering, chunking, noise headers, indexing.yaml</p>
                  </div>
                  <div className="feature-card">
                    <h4>Web Context Integration</h4>
                    <p>DuckDuckGo search + heuristics — external snippets for context expansion</p>
                  </div>
                  <div className="feature-card">
                    <h4>Observability</h4>
                    <p>Traces with token estimates, RSS monitoring, step-by-step agent debugging</p>
                  </div>
                  <div className="feature-card">
                    <h4>Multi-Port Architecture</h4>
                    <p>8080 (main app), 8087 (build proxy when enabled) — auxiliary services on their own ports</p>
                  </div>
                </div>
              </div>
            )}
            {infoSubTab === 'architecture' && (
              <div className="dashboard-section-inner">
                <h3>Architecture Overview</h3>
                <p className="architecture-intro">
                  ChironAI is built on a <strong>modular, domain-driven architecture</strong> with clear separation of concerns.
                  The system is designed for maintainability, testability, and domain flexibility—swap knowledge domains without touching core logic.
                </p>
                
                <div className="architecture-section">
                  <h4>Core Layers (Hexagonal Design)</h4>
                  <div className="architecture-grid">
                    <div className="arch-layer-card arch-layer-api">
                      <div className="arch-layer-icon">📡</div>
                      <h5>Presentation</h5>
                      <p>HTTP routes (Flask), CLI entrypoints, API blueprints. Zero infrastructure imports—uses application use cases only.</p>
                    </div>
                    <div className="arch-layer-card arch-layer-application">
                      <div className="arch-layer-icon">⚙️</div>
                      <h5>Application</h5>
                      <p>Use cases (RAG, crawl, ingestion), container/wiring, DTOs. Orchestrates domain services and ports.</p>
                    </div>
                    <div className="arch-layer-card arch-layer-domain">
                      <div className="arch-layer-icon">🎯</div>
                      <h5>Domain</h5>
                      <p>Entities (RagChunk, CrawlSource), services (retrieval, rerank, chunking), ports (repositories, providers). Pure business logic—no external dependencies.</p>
                    </div>
                    <div className="arch-layer-card arch-layer-infrastructure">
                      <div className="arch-layer-icon">🏗️</div>
                      <h5>Infrastructure</h5>
                      <p>Adapters: Qdrant (RagRepository), Ollama (embed/chat/rerank), FS (MarkdownStore), Playwright (crawl), logging.</p>
                    </div>
                  </div>
                </div>

                <div className="architecture-section">
                  <h4>CoreModules (Independent Services)</h4>
                  <div className="modules-grid">
                    <div className="module-card">
                      <h5>RagService</h5>
                      <p>Full RAG pipeline: retrieval → rerank → prompt → LLM answer. pip: <code>chironai-rag-service</code></p>
                    </div>
                    <div className="module-card">
                      <h5>LlmProxy</h5>
                      <p>OpenAI + Anthropic API compatibility. Build presets, streaming synthesis, autocomplete model. pip: <code>llm-proxy</code></p>
                    </div>
                    <div className="module-card">
                      <h5>MdIngestionService</h5>
                      <p>Config-driven markdown preprocessing: filtering, chunking, noise removal. Feeds RAG via HTTP contract.</p>
                    </div>
                    <div className="module-card">
                      <h5>ServiceStarter</h5>
                      <p>Auto-install/start: Docker Desktop, Ollama, Qdrant, Open WebUI (Windows). pip: <code>service-starter</code></p>
                    </div>
                    <div className="module-card">
                      <h5>WebInteraction</h5>
                      <p>External context: DuckDuckGo search, snippet extraction, trigger heuristics. pip: <code>web-interaction</code></p>
                    </div>
                  </div>
                </div>

                <div className="architecture-section">
                  <h4>Data Flow (Request Lifecycle)</h4>
                  <div className="data-flow-diagram">
                    <div className="flow-step">
                      <span className="flow-label">Client</span>
                      <span className="flow-arrow">→</span>
                    </div>
                    <div className="flow-step">
                      <span className="flow-label">API Layer</span>
                      <span className="flow-arrow">→</span>
                    </div>
                    <div className="flow-step">
                      <span className="flow-label">Use Cases</span>
                      <span className="flow-arrow">→</span>
                    </div>
                    <div className="flow-step">
                      <span className="flow-label">Domain Services</span>
                      <span className="flow-arrow">→</span>
                    </div>
                    <div className="flow-step">
                      <span className="flow-label">Ports</span>
                      <span className="flow-arrow">→</span>
                    </div>
                    <div className="flow-step">
                      <span className="flow-label">Infrastructure</span>
                    </div>
                  </div>
                </div>

                <div className="architecture-principles">
                  <h4>Design Principles</h4>
                  <ul className="principle-list">
                    <li><strong>Dependency Rule:</strong> Domain → never imports Application, API, or Infrastructure. Enforced by import-linter contracts.</li>
                    <li><strong>Module Isolation:</strong> CoreModules communicate via HTTP contracts or interfaces (Protocol/ABC), never direct imports.</li>
                    <li><strong>Domain Agnostic:</strong> Swap knowledge domains (Apple → any) by changing sources and prompts—no core code changes.</li>
                    <li><strong>Testability:</strong> Domain/application tests use mocks; API tests use Flask client with wired use cases.</li>
                    <li><strong>Local-First:</strong> All services (Ollama, Qdrant) run locally via Docker. Optional cloud LLM fallback.</li>
                  </ul>
                </div>
              </div>
            )}
            {infoSubTab === 'quick-start' && (
              <div className="dashboard-section-inner">
                <h3>Quick Start</h3>
                <p className="quick-start-intro">
                  Get ChironAI running in 5 steps. Requires Python 3.10+, Docker Desktop (Windows), and Ollama.
                </p>

                <div className="quick-start-grid">
                  <div className="quick-start-card">
                    <div className="qs-number">1</div>
                    <div className="qs-content">
                      <h4>Install Dependencies</h4>
                      <p>Install Python dependencies from the repository root:</p>
                      <code>pip install -r requirements-dev.txt</code>
                      <p className="qs-hint">This installs <code>chironai</code> in editable mode plus dev tools (pytest, ruff, import-linter).</p>
                    </div>
                  </div>

                  <div className="quick-start-card">
                    <div className="qs-number">2</div>
                    <div className="qs-content">
                      <h4>Start Infrastructure</h4>
                      <p>Use ServiceStarter to auto-install and start services:</p>
                      <code>python -m servicestarter start-all</code>
                      <p className="qs-hint">Installs Docker Desktop, Ollama, and starts Qdrant container. Windows-only; manual setup on other OS.</p>
                    </div>
                  </div>

                  <div className="quick-start-card">
                    <div className="qs-number">3</div>
                    <div className="qs-content">
                      <h4>Configure Sources</h4>
                      <p>Edit <code>config/crawler.yaml</code> and <code>config/indexing.yaml</code> to add documentation sources:</p>
                      <code>sources: [apple_docs, wwdc_sessions, ...]</code>
                      <p className="qs-hint">Default sources include Apple Developer Documentation and WWDC transcripts.</p>
                    </div>
                  </div>

                  <div className="quick-start-card">
                    <div className="qs-number">4</div>
                    <div className="qs-content">
                      <h4>Crawl & Index</h4>
                      <p>Crawl sources and build the RAG index:</p>
                      <code>python WebUI/app.py crawl</code>
                      <code>python WebUI/app.py index</code>
                      <p className="qs-hint">Monitor progress in the WebUI Crawler/Indexer tabs. Embeddings use Ollama.</p>
                    </div>
                  </div>

                  <div className="quick-start-card">
                    <div className="qs-number">5</div>
                    <div className="qs-content">
                      <h4>Launch WebUI</h4>
                      <p>Start the WebUI server and open in browser:</p>
                      <code>.\start_webui.bat</code>
                      <p className="qs-hint">Access at <code>http://localhost:8080</code>. Use RAG tab to test queries.</p>
                    </div>
                  </div>
                </div>

                <div className="quick-start-prerequisites">
                  <h4>Prerequisites</h4>
                  <div className="prereq-list">
                    <div className="prereq-item">
                      <div>
                        <strong>Python 3.10–3.13</strong>
                        <p>Verify with <code>python --version</code></p>
                      </div>
                    </div>
                    <div className="prereq-item">
                      <div>
                        <strong>Docker Desktop</strong>
                        <p>Required for Qdrant (Windows). Manual install on macOS/Linux.</p>
                      </div>
                    </div>
                    <div className="prereq-item">
                      <div>
                        <strong>Ollama</strong>
                        <p>Local LLM provider. Pull models: <code>ollama pull llama3.2</code></p>
                      </div>
                    </div>
                    <div className="prereq-item">
                      <div>
                        <strong>Config Files</strong>
                        <p>Review <code>config/rag.yaml</code>, <code>config/models.yaml</code>, <code>config/server.yaml</code></p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="quick-start-troubleshooting">
                  <h4>First Steps After Setup</h4>
                  <div className="troubleshooting-list">
                    <div className="troubleshooting-item">
                      <div>
                        <strong>RAG Tab</strong>
                        <p>Verify Qdrant connection and collection status</p>
                      </div>
                    </div>
                    <div className="troubleshooting-item">
                      <div>
                        <strong>Model Tester</strong>
                        <p>Ask a question to test RAG retrieval</p>
                      </div>
                    </div>
                    <div className="troubleshooting-item">
                      <div>
                        <strong>Settings</strong>
                        <p>Configure chat model, embedding model, rerank settings</p>
                      </div>
                    </div>
                    <div className="troubleshooting-item">
                      <div>
                        <strong>LLM Proxy</strong>
                        <p>Test OpenAI/Anthropic-compatible API endpoints</p>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            )}
            {infoSubTab === 'credits' && (
              <div className="dashboard-section-inner">
                <h3>Credits & Acknowledgments</h3>
                <p className="credits-intro">
                  ChironAI is built with contributions from multiple projects and technologies. 
                  We gratefully acknowledge the following:
                </p>

                <div className="credits-section">
                  <h4>Core Projects</h4>
                  <div className="credit-cards">
                    <div className="credit-card">
                      <h5>RagService</h5>
                      <p>Full RAG pipeline: retrieval → rerank → prompt → LLM answer generation.</p>
                      <code>pip: chironai-rag-service</code>
                    </div>
                    <div className="credit-card">
                      <h5>LlmProxy</h5>
                      <p>OpenAI + Anthropic API compatibility layer with streaming synthesis.</p>
                      <code>pip: llm-proxy</code>
                    </div>
                    <div className="credit-card">
                      <h5>ServiceStarter</h5>
                      <p>Auto-install/start: Docker Desktop, Ollama, Qdrant, Open WebUI (Windows).</p>
                      <code>pip: service-starter</code>
                    </div>
                    <div className="credit-card">
                      <h5>WebInteraction</h5>
                      <p>External context: DuckDuckGo search, snippet extraction, trigger heuristics.</p>
                      <code>pip: web-interaction</code>
                    </div>
                  </div>
                </div>

                <div className="credits-section">
                  <h4>Infrastructure & Dependencies</h4>
                  <ul className="credits-list">
                    <li><strong>Ollama</strong> — Local LLM provider for running models locally</li>
                    <li><strong>Qdrant</strong> — Vector database for RAG embeddings</li>
                    <li><strong>Docker Desktop</strong> — Containerization for infrastructure services</li>
                    <li><strong>Flask</strong> — Python web framework for API layer</li>
                    <li><strong>React + Vite</strong> — Modern frontend framework and build tool</li>
                    <li><strong>Material 3 Design</strong> — Design system for UI components</li>
                  </ul>
                </div>

                <div className="credits-section">
                  <h4>Documentation Sources</h4>
                  <p>Default configuration targets Apple ecosystem documentation:</p>
                  <ul className="credits-list">
                    <li>Apple Developer Documentation (iOS, macOS, Swift, SwiftUI, UIKit)</li>
                    <li>Swift Concurrency & Observation framework docs</li>
                    <li>Extensible to any domain via configuration</li>
                  </ul>
                </div>

                <div className="credits-section">
                  <h4>Project Status</h4>
                  <p>
                    ChironAI is a proprietary modular RAG platform.
                    The architecture is designed for flexibility—swap knowledge domains without core code changes.
                  </p>
                </div>
              </div>
            )}
          </div>
        </section>
        <section className="dashboard-info-card dashboard-proxy-guide-card" aria-label="CLI proxy onboarding">
          <div className="dashboard-info-card-header">
            <h2 className="dashboard-info-card-title">CLI via RAG Fusion Proxy</h2>
            <p className="dashboard-info-card-subtitle">
              Run Claude Code and Codex through ChironAI for shared builds, RAG context, and proxy traces.
            </p>
          </div>
          <div className="dashboard-info-subtabs" role="tablist" aria-label="Proxy onboarding sections">
            {PROXY_GUIDE_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                className={`dashboard-info-subtab ${proxyGuideTab === tab.id ? 'dashboard-info-subtab-active' : ''}`}
                role="tab"
                aria-selected={proxyGuideTab === tab.id}
                onClick={() => setProxyGuideTab(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="dashboard-info-panel dashboard-proxy-guide-panel" role="tabpanel">
            {proxyGuideTab === 'why' && (
              <div className="dashboard-section-inner">
                <h3>Why route CLI traffic through this proxy</h3>
                <ul className="dashboard-proxy-guide-list">
                  <li>
                    <strong>Single build id contract:</strong> your CLI uses the same model ids configured in{' '}
                    <strong>LLM Proxy</strong> builds.
                  </li>
                  <li>
                    <strong>RAG + prompt policy:</strong> requests go through the same retrieval and prompt assembly as WebUI.
                  </li>
                  <li>
                    <strong>Observability:</strong> requests appear in Logs, Traces, and Journal for faster debugging.
                  </li>
                  <li>
                    <strong>One local endpoint:</strong> both OpenAI and Anthropic-style clients can point to the same proxy base URL.
                  </li>
                </ul>
              </div>
            )}
            {proxyGuideTab === 'claude' && (
              <div className="dashboard-section-inner">
                <h3>Claude Code launch (Windows)</h3>
                <p>From repository root, start Claude with proxy env preconfigured:</p>
                <code className="dashboard-proxy-guide-code">.\start_claude_proxy.bat --model your-build-id</code>
                <p>PowerShell variant:</p>
                <code className="dashboard-proxy-guide-code">.\start_claude_proxy.ps1 --model your-build-id</code>
                <p className="dashboard-proxy-guide-hint">
                  Default proxy base URL: <code>http://127.0.0.1:8080</code>. Override with{' '}
                  <code>CHIRON_PROXY_BASE_URL</code> before launch.
                </p>
              </div>
            )}
            {proxyGuideTab === 'codex' && (
              <div className="dashboard-section-inner">
                <h3>Codex launch (Windows)</h3>
                <p>Start Codex with OpenAI-compatible proxy variables:</p>
                <code className="dashboard-proxy-guide-code">.\start_codex_proxy.bat --model your-build-id</code>
                <p>PowerShell variant:</p>
                <code className="dashboard-proxy-guide-code">.\start_codex_proxy.ps1 --model your-build-id</code>
                <p className="dashboard-proxy-guide-hint">
                  The scripts set <code>OPENAI_BASE_URL</code> / <code>OPENAI_API_BASE</code> to the proxy host for the current run.
                </p>
              </div>
            )}
            {proxyGuideTab === 'configured' && (
              <div className="dashboard-section-inner">
                <h3>Configured launch (no required arguments)</h3>
                <p>
                  Edit <code>start_claude_proxy_configured.ps1</code> and <code>start_codex_proxy_configured.ps1</code>{' '}
                  once, then launch with:
                </p>
                <code className="dashboard-proxy-guide-code">.\start_claude_proxy_configured.bat</code>
                <code className="dashboard-proxy-guide-code">.\start_codex_proxy_configured.bat</code>

                <div className="dashboard-proxy-customizer">
                  <label className="dashboard-proxy-customizer-field">
                    Preset
                    <select
                      className="dashboard-card-field"
                      value={proxyPresetId}
                      onChange={(e) => {
                        const id = e.target.value;
                        const preset = PROXY_CUSTOM_PRESETS.find((x) => x.id === id);
                        setProxyPresetId(id);
                        if (!preset) return;
                        setConfiguredBaseUrl(preset.baseUrl);
                        setConfiguredBuildId(preset.buildId);
                        setConfiguredAuthToken(preset.authToken);
                        setConfiguredOpenAiApiKey(preset.openAiApiKey);
                      }}
                    >
                      {PROXY_CUSTOM_PRESETS.map((preset) => (
                        <option key={preset.id} value={preset.id}>
                          {preset.label}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="dashboard-proxy-customizer-field">
                    Proxy base URL
                    <input
                      className="dashboard-card-field"
                      value={configuredBaseUrl}
                      onChange={(e) => setConfiguredBaseUrl(e.target.value)}
                    />
                  </label>
                  <label className="dashboard-proxy-customizer-field">
                    Build id
                    {availableBuildIds.length > 0 ? (
                      <select
                        className="dashboard-card-field"
                        value={configuredBuildId}
                        onChange={(e) => setConfiguredBuildId(e.target.value)}
                      >
                        {availableBuildIds.map((buildId) => (
                          <option key={buildId} value={buildId}>
                            {buildId}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        className="dashboard-card-field"
                        value={configuredBuildId}
                        onChange={(e) => setConfiguredBuildId(e.target.value)}
                        placeholder="No builds found yet"
                      />
                    )}
                  </label>
                  <label className="dashboard-proxy-customizer-field">
                    Claude auth token
                    <input
                      className="dashboard-card-field"
                      value={configuredAuthToken}
                      onChange={(e) => setConfiguredAuthToken(e.target.value)}
                    />
                  </label>
                  <label className="dashboard-proxy-customizer-field">
                    Codex API key
                    <input
                      className="dashboard-card-field"
                      value={configuredOpenAiApiKey}
                      onChange={(e) => setConfiguredOpenAiApiKey(e.target.value)}
                    />
                  </label>
                </div>

                <p className="dashboard-proxy-guide-hint">Use these values in *_configured.ps1 files:</p>
                <pre className="dashboard-proxy-guide-pre">
{`# start_claude_proxy_configured.ps1
$ConfiguredBaseUrl = "${configuredBaseUrl}"
$ConfiguredModel = "${configuredBuildId}"
$ConfiguredAuthToken = "${configuredAuthToken}"

# start_codex_proxy_configured.ps1
$ConfiguredBaseUrl = "${configuredBaseUrl}"
$ConfiguredModel = "${configuredBuildId}"
$ConfiguredOpenAiApiKey = "${configuredOpenAiApiKey}"`}
                </pre>
              </div>
            )}
            {proxyGuideTab === 'checks' && (
              <div className="dashboard-section-inner">
                <h3>Quick verification checklist</h3>
                <ul className="dashboard-proxy-guide-list">
                  <li>
                    Ensure your target build exists in <strong>LLM Proxy</strong> tab and use its <code>id</code> in{' '}
                    <code>--model</code>.
                  </li>
                  <li>
                    Open <strong>RAG Fusion Proxy</strong> and verify status base URL points to your current host/port.
                  </li>
                  <li>
                    Run <code>GET /v1/models</code> against proxy and confirm your build id is listed.
                  </li>
                  <li>
                    Send one CLI request and confirm new entries appear in <strong>Logs</strong> and <strong>Traces</strong>.
                  </li>
                </ul>
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}

export default DashboardTab;
