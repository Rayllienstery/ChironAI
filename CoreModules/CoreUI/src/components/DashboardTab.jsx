import React, { useEffect, useState, useCallback } from 'react';
import PipelineCiDiagram from './PipelineCiDiagram';
import { useMergedPipelinePreview } from '../hooks/useMergedPipelinePreview';
import { getModelSettings, getRagStatus, getClawCodeStatus, getClawCodeSettings, getRagCollections } from '../services/api';
import '../styles/components/DashboardTab.css';

const INFO_TABS = [
  { id: 'intro', label: 'Intro' },
  { id: 'features', label: 'Features' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'quick-start', label: 'Quick Start' },
  { id: 'reference', label: 'Reference' },
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

function DashboardClawProxyCard({ onNavigate }) {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(null);
  const [status, setStatus] = useState(null);
  const [settings, setSettings] = useState(null);
  const [collections, setCollections] = useState([]);

  const load = useCallback(async () => {
    setLoadError(null);
    try {
      const [statusData, settingsData, colData] = await Promise.all([
        getClawCodeStatus(),
        getClawCodeSettings().catch(() => null),
        getRagCollections().catch(() => ({ collections: [] })),
      ]);
      setStatus(statusData || {});
      setSettings(settingsData || {});
      setCollections(colData.collections || []);
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

  const collectionNames = collections.map((c) => c.name).filter(Boolean);
  const collectionSelectValue =
    collectionNames.length > 0 && collectionNames.includes((settings?.rag_collection || '').trim())
      ? settings?.rag_collection
      : '';

  return (
    <section className="app-default-card dashboard-proxy-card" aria-labelledby="dashboard-claw-proxy-heading">
      <div className="dashboard-card-header">
        <h2 id="dashboard-claw-proxy-heading">Claw Proxy</h2>
        <div className="dashboard-card-actions">
          <button type="button" className="dashboard-primary-btn" onClick={() => onNavigate('claw-proxy')}>
            Open Claw Proxy
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
      {!loading && !loadError && status && (
        <div className="dashboard-proxy-sections">
          <div className="dashboard-proxy-block">
            <h3 className="dashboard-proxy-block-title">Status</h3>
            {row('Enabled', String(status.enabled))}
            {row('Base URL', status.openai_base_url)}
            {row('Health', `${status.openai_base_url}/health`)}
          </div>
          <div className="dashboard-proxy-block">
            <h3 className="dashboard-proxy-block-title">ClawCode</h3>
            {row('Max agent steps (YAML/env)', settings?.max_agent_steps ?? '—')}
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

  const go = (tabId) => {
    if (typeof onNavigate === 'function') onNavigate(tabId);
  };

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
                    <h3> Experimental Project</h3>
                    <p>
                      <strong>ChironAI is a deeply experimental project</strong> provided as-is. It is specifically
                      designed for developing applications within the Apple ecosystem (iOS, macOS, Swift, SwiftUI,
                      UIKit, Observation, etc.) and addresses the specific challenges of Apple platform development.
                    </p>
                    <p>
                      This tool focuses on solving the pain points of Apple development by providing accurate, up-to-date
                      documentation and best practices through RAG, ensuring code quality and architectural compliance for
                      Apple platforms.
                    </p>
                  </div>
                </div>
                <div className="dashboard-section-inner">
                  <h3>What is ChironAI?</h3>
                  <p>
                    ChironAI is a local, model-agnostic RAG (Retrieval-Augmented Generation) layer designed for developers.
                    It works with any reasonable LLM (local or cloud, 7B–70B) and provides accurate, up-to-date knowledge
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
                    <p>Works with any LLM (local or cloud, 7B–70B models)</p>
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
                </div>
              </div>
            )}
            {infoSubTab === 'architecture' && (
              <div className="dashboard-section-inner">
                <h3>Architecture Overview</h3>
                <p>The codebase follows a clean layered architecture:</p>
                <div className="architecture-list">
                  <div className="architecture-item">
                    <strong>api/</strong> — Presentation layer (HTTP routes, CLI entrypoints)
                  </div>
                  <div className="architecture-item">
                    <strong>application/</strong> — Application layer (use cases, container/wiring)
                  </div>
                  <div className="architecture-item">
                    <strong>domain/</strong> — Domain layer (entities, services, ports, errors)
                  </div>
                  <div className="architecture-item">
                    <strong>infrastructure/</strong> — Infrastructure layer (Qdrant, Ollama, FS, crawl, logging)
                  </div>
                  <div className="architecture-item">
                    <strong>config/</strong> — Configuration (YAML + env)
                  </div>
                  <div className="architecture-item">
                    <strong>utils/</strong> — Pure helpers
                  </div>
                </div>
                <p className="architecture-note">
                  Each layer only depends on the layer below it. The Domain layer must not depend on UI or infrastructure.
                </p>
              </div>
            )}
            {infoSubTab === 'quick-start' && (
              <div className="dashboard-section-inner">
                <h3>Quick Start</h3>
                <div className="quick-start-steps">
                  <div className="step">
                    <div className="step-number">1</div>
                    <div className="step-content">
                      <h4>Install Dependencies</h4>
                      <p>
                        Install Python dependencies: <code>python -m pip install -r WebUI\requirements.txt</code>
                      </p>
                    </div>
                  </div>
                  <div className="step">
                    <div className="step-number">2</div>
                    <div className="step-content">
                      <h4>Start Services</h4>
                      <p>
                        Ensure Ollama is running on <code>http://localhost:11434</code> and Qdrant on{' '}
                        <code>http://localhost:6333</code>
                      </p>
                    </div>
                  </div>
                  <div className="step">
                    <div className="step-number">3</div>
                    <div className="step-content">
                      <h4>Run Crawler</h4>
                      <p>
                        Crawl documentation sources: <code>python tmrag.py crawl</code>
                      </p>
                    </div>
                  </div>
                  <div className="step">
                    <div className="step-number">4</div>
                    <div className="step-content">
                      <h4>Index Content</h4>
                      <p>
                        Index crawled content: <code>python tmrag.py index</code>
                      </p>
                    </div>
                  </div>
                  <div className="step">
                    <div className="step-number">5</div>
                    <div className="step-content">
                      <h4>Start WebUI</h4>
                      <p>
                        Launch the WebUI: <code>python tmrag.py start</code> or <code>.\start_webui.bat</code>
                      </p>
                    </div>
                  </div>
                </div>
              </div>
            )}
            {infoSubTab === 'reference' && (
              <>
                <div className="dashboard-section-inner">
                  <h3>Navigation Guide</h3>
                  <div className="navigation-cards">
                    <div className="nav-card">
                      <h4>Crawler / Indexer</h4>
                      <p>Manage crawl sources, view crawled pages, and create RAG collections from sources.</p>
                    </div>
                    <div className="nav-card">
                      <h4>RAG / Qdrant</h4>
                      <p>View RAG collections, check Qdrant status, and manage vector database.</p>
                    </div>
                    <div className="nav-card">
                      <h4>Model Tester</h4>
                      <p>Test LLM models with RAG context, evaluate responses, and debug retrieval.</p>
                    </div>
                    <div className="nav-card">
                      <h4>Template Editor</h4>
                      <p>Edit and manage RAG system prompts and templates for different scenarios.</p>
                    </div>
                    <div className="nav-card">
                      <h4>Logs</h4>
                      <p>View application logs, RAG retrieval logs, and system events.</p>
                    </div>
                    <div className="nav-card">
                      <h4>Settings</h4>
                      <p>Configure theme, accent colors, and application preferences.</p>
                    </div>
                  </div>
                </div>
                <div className="dashboard-section-inner">
                  <h3>CLI Commands</h3>
                  <div className="cli-commands">
                    <div className="cli-command">
                      <code>python tmrag.py start</code>
                      <span>Start WebUI (Flask)</span>
                    </div>
                    <div className="cli-command">
                      <code>python tmrag.py crawl</code>
                      <span>Run crawler to fetch documentation</span>
                    </div>
                    <div className="cli-command">
                      <code>python tmrag.py index</code>
                      <span>Index crawled content into RAG</span>
                    </div>
                    <div className="cli-command">
                      <code>python tmrag.py rebuild</code>
                      <span>Full index rebuild</span>
                    </div>
                    <div className="cli-command">
                      <code>python tmrag.py update</code>
                      <span>Crawl and index in one command</span>
                    </div>
                    <div className="cli-command">
                      <code>python tmrag.py ingest &lt;dir&gt;</code>
                      <span>Index local directory</span>
                    </div>
                    <div className="cli-command">
                      <code>python tmrag.py proxy</code>
                      <span>Start RAG proxy (OpenAI-compatible)</span>
                    </div>
                    <div className="cli-command">
                      <code>python tmrag.py test</code>
                      <span>Run pytest tests</span>
                    </div>
                  </div>
                </div>
                <div className="dashboard-section-inner">
                  <h3>Documentation</h3>
                  <p>For more detailed information, refer to the documentation files in the project:</p>
                  <ul className="docs-list">
                    <li>
                      <strong>README.md</strong> — Project overview and mission
                    </li>
                    <li>
                      <strong>docs/ARCHITECTURE.md</strong> — Detailed architecture documentation
                    </li>
                    <li>
                      <strong>QUICK_START.md</strong> — Quick start guide
                    </li>
                    <li>
                      <strong>SETUP_INSTRUCTIONS.md</strong> — Installation and setup instructions
                    </li>
                    <li>
                      <strong>TODO.md</strong> — Development roadmap and tasks
                    </li>
                  </ul>
                </div>
                <div className="dashboard-section-inner">
                  <h3>Tips</h3>
                  <div className="tips-list">
                    <div className="tip-item">
                      <strong>System Status:</strong> Check the header for Ollama and Qdrant status. Both services should be
                      running for full functionality.
                    </div>
                    <div className="tip-item">
                      <strong>First Time Setup:</strong> Start by crawling documentation sources, then index them before
                      testing models.
                    </div>
                    <div className="tip-item">
                      <strong>Model Selection:</strong> The system works with any LLM. Configure models in{' '}
                      <code>config/models.yaml</code>.
                    </div>
                    <div className="tip-item">
                      <strong>RAG Quality:</strong> For best results, ensure your collections are properly indexed and
                      contain relevant documentation.
                    </div>
                    <div className="tip-item">
                      <strong>Debugging:</strong> Use the Logs tab to monitor RAG retrieval, check chunk scores, and debug
                      issues.
                    </div>
                  </div>
                </div>
              </>
            )}
          </div>
        </section>

        <div className="dashboard-bottom-grid">
          <DashboardLlmProxyCard
            onNavigate={go}
            onOpenLogs={onOpenLogs}
            onOpenLlmProxyAutocomplete={onOpenLlmProxyAutocomplete}
          />
          <DashboardClawProxyCard onNavigate={go} />
          <DashboardRagCard onNavigate={go} />
        </div>
      </div>
    </div>
  );
}

export default DashboardTab;
