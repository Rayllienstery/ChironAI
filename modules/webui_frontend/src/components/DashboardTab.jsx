import React from 'react';
import './DashboardTab.css';

function DashboardTab() {
  return (
    <div className="dashboard-tab">
      <div className="dashboard-header">
        <h2>Welcome to TMRagFetcher</h2>
        <p className="dashboard-subtitle">Local, model-agnostic RAG layer for developers</p>
      </div>

      <div className="dashboard-content">
        <section className="dashboard-section notice-section">
          <div className="notice-content">
            <h3> Experimental Project</h3>
            <p>
              <strong>TMRagFetcher is a deeply experimental project</strong> provided as-is. 
              It is specifically designed for developing applications within the Apple ecosystem (iOS, macOS, Swift, SwiftUI, UIKit, Observation, etc.) 
              and addresses the specific challenges of Apple platform development.
            </p>
            <p>
              This tool focuses on solving the pain points of Apple development by providing accurate, 
              up-to-date documentation and best practices through RAG, ensuring code quality and architectural compliance 
              for Apple platforms.
            </p>
          </div>
        </section>

        <section className="dashboard-section">
          <h3>What is TMRagFetcher?</h3>
          <p>
            TMRagFetcher is a local, model-agnostic RAG (Retrieval-Augmented Generation) layer designed for developers.
            It works with any reasonable LLM (local or cloud, 7B–70B) and provides accurate, up-to-date knowledge
            through a modular fetcher/crawler and RAG system.
          </p>
          <p>
            The system delivers predictable, engineering-focused results with strict response structure
            (RAG facts → implementation → summary), adherence to architecture (Clean/MVVM), Swift 6 strict concurrency,
            Observation, UI rules, and controlled variability (minimal randomness in generation).
          </p>
        </section>

        <section className="dashboard-section">
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
        </section>

        <section className="dashboard-section">
          <h3>Architecture Overview</h3>
          <p>
            The codebase follows a clean layered architecture:
          </p>
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
        </section>

        <section className="dashboard-section">
          <h3>Quick Start</h3>
          <div className="quick-start-steps">
            <div className="step">
              <div className="step-number">1</div>
              <div className="step-content">
                <h4>Install Dependencies</h4>
                <p>Install Python dependencies: <code>python -m pip install -r WebUI\requirements.txt</code></p>
              </div>
            </div>
            <div className="step">
              <div className="step-number">2</div>
              <div className="step-content">
                <h4>Start Services</h4>
                <p>Ensure Ollama is running on <code>http://localhost:11434</code> and Qdrant on <code>http://localhost:6333</code></p>
              </div>
            </div>
            <div className="step">
              <div className="step-number">3</div>
              <div className="step-content">
                <h4>Run Crawler</h4>
                <p>Crawl documentation sources: <code>python tmrag.py crawl</code></p>
              </div>
            </div>
            <div className="step">
              <div className="step-number">4</div>
              <div className="step-content">
                <h4>Index Content</h4>
                <p>Index crawled content: <code>python tmrag.py index</code></p>
              </div>
            </div>
            <div className="step">
              <div className="step-number">5</div>
              <div className="step-content">
                <h4>Start WebUI</h4>
                <p>Launch the WebUI: <code>python tmrag.py start</code> or <code>.\start_webui.bat</code></p>
              </div>
            </div>
          </div>
        </section>

        <section className="dashboard-section">
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
        </section>

        <section className="dashboard-section">
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
        </section>

        <section className="dashboard-section">
          <h3>Documentation</h3>
          <p>
            For more detailed information, refer to the documentation files in the project:
          </p>
          <ul className="docs-list">
            <li><strong>README.md</strong> — Project overview and mission</li>
            <li><strong>docs/ARCHITECTURE.md</strong> — Detailed architecture documentation</li>
            <li><strong>QUICK_START.md</strong> — Quick start guide</li>
            <li><strong>SETUP_INSTRUCTIONS.md</strong> — Installation and setup instructions</li>
            <li><strong>TODO.md</strong> — Development roadmap and tasks</li>
          </ul>
        </section>

        <section className="dashboard-section">
          <h3>Tips</h3>
          <div className="tips-list">
            <div className="tip-item">
              <strong>System Status:</strong> Check the header for Ollama and Qdrant status. Both services should be running for full functionality.
            </div>
            <div className="tip-item">
              <strong>First Time Setup:</strong> Start by crawling documentation sources, then index them before testing models.
            </div>
            <div className="tip-item">
              <strong>Model Selection:</strong> The system works with any LLM. Configure models in <code>config/models.yaml</code>.
            </div>
            <div className="tip-item">
              <strong>RAG Quality:</strong> For best results, ensure your collections are properly indexed and contain relevant documentation.
            </div>
            <div className="tip-item">
              <strong>Debugging:</strong> Use the Logs tab to monitor RAG retrieval, check chunk scores, and debug issues.
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}

export default DashboardTab;

