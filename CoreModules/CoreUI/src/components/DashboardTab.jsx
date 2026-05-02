import { useState } from 'react';
import CoreUISubtabs from './CoreUISubtabs';
import '../styles/components/DashboardTab.css';

const INFO_TABS = [
  { id: 'intro', label: 'Intro' },
  { id: 'features', label: 'Features' },
  { id: 'architecture', label: 'Architecture' },
  { id: 'quick-start', label: 'Quick Start' },
  { id: 'credits', label: 'Credits' },
];

function DashboardTab({ onNavigate, onOpenLogs, onOpenLlmProxyAutocomplete }) {
  const [infoSubTab, setInfoSubTab] = useState('intro');

  const go = (tabId) => {
    if (typeof onNavigate === 'function') onNavigate(tabId);
  };

  return (
    <div className="dashboard-tab tab-view">
      <div className="dashboard-layout">
        <section className="dashboard-info-card" aria-label="About ChironAI">
          <div className="dashboard-info-card-header">
            <h2 className="dashboard-info-card-title">ChironAI</h2>
            <p className="dashboard-info-card-subtitle">Local, model-agnostic RAG layer for developers</p>
          </div>
          <CoreUISubtabs
            tabs={INFO_TABS}
            value={infoSubTab}
            onChange={(id) => setInfoSubTab(id)}
            ariaLabel="About sections"
            className="dashboard-info-subtabs"
          />
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
                    <p>SSE for OpenAI and Anthropic formats — streaming even when model doesn&apos;t support it</p>
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
                      <p>Auto-install/start: Docker Desktop, Ollama, Qdrant (Windows). pip: <code>service-starter</code></p>
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
                      <p>Auto-install/start: Docker Desktop, Ollama, Qdrant (Windows).</p>
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

        <section className="dashboard-info-card dashboard-proxy-hint-card" aria-label="RAG Fusion Proxy HTTP clients">
          <div className="dashboard-info-card-header">
            <h2 className="dashboard-info-card-title">RAG Fusion Proxy</h2>
            <p className="dashboard-info-card-subtitle">
              HTTP client setup (OpenAI and Anthropic-style endpoints, build ids, env vars) is on{' '}
              <strong>RAG Fusion Proxy</strong> → <strong>Overview</strong>.
            </p>
          </div>
          <div className="dashboard-section-inner">
            <p className="dashboard-card-muted">
              Open the tab for base URL, models list, and integration notes. Logs and traces stay in their respective tabs.
            </p>
            <div className="dashboard-proxy-hint-actions">
              <button type="button" className="dashboard-text-btn" onClick={() => go('rag-fusion-proxy')}>
                Open RAG Fusion Proxy
              </button>
              {typeof onOpenLogs === 'function' && (
                <button type="button" className="dashboard-text-btn" onClick={() => onOpenLogs()}>
                  View Logs
                </button>
              )}
              {typeof onOpenLlmProxyAutocomplete === 'function' && (
                <button type="button" className="dashboard-text-btn" onClick={() => onOpenLlmProxyAutocomplete()}>
                  Autocomplete settings
                </button>
              )}
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export default DashboardTab;
