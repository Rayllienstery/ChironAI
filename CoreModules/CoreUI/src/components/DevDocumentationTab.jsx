import { useState } from "react";
import CoreUIBadge from "./CoreUIBadge";
import CoreUIPillTabs from "./CoreUIPillTabs";
import "../styles/components/ExtensionsTab.css";
import "../styles/components/DashboardTab.css";
import "../styles/components/SettingsTab.css";

const SUB_TABS = [
  { id: "overview", label: "Overview" },
  { id: "architecture", label: "Architecture" },
];

export default function DevDocumentationTab() {
  const [subTab, setSubTab] = useState("overview");

  return (
    <div className="extensions-tab tab-view">
      <div className="extensions-tab__header">
        <div>
          <h2>Dev Documentation</h2>
          <p>Guide for integrating extensions and understanding system architecture.</p>
        </div>
      </div>

      <div className="coreui-mt-md coreui-mb-lg">
        <CoreUIPillTabs
          tabs={SUB_TABS}
          value={subTab}
          onChange={setSubTab}
          ariaLabel="Documentation sections"
        />
      </div>

      <div className="extensions-dev-doc">
        {subTab === "overview" && (
          <>
            <section className="coreui-card-shell coreui-p-md extensions-schema-section">
              <div className="extensions-schema-section-header">
                <h4>Overview</h4>
              </div>
              <div className="extensions-schema-section-body">
                <p>
                  Extensions allow you to add new functionality to the project, such as new LLM providers,
                  UI tabs, or background services. They are discovered via a manifest file and can
                  provide both backend logic (Python) and frontend UI (declarative schemas).
                </p>
              </div>
            </section>

            <section className="coreui-card-shell coreui-p-md extensions-schema-section">
              <div className="extensions-schema-section-header">
                <h4>Manifest (chironai-extension.json)</h4>
              </div>
              <div className="extensions-schema-section-body">
                <p>Every extension must have a <code>chironai-extension.json</code> in its root directory.</p>
                <pre className="extensions-schema-diagnostics">
{`{
  "id": "my-extension",
  "version": "0.1.0",
  "type": "ui_extension", // or "llm_provider"
  "title": "My Extension",
  "backend": {
    "entrypoint": "backend.provider:create_provider"
  },
  "capabilities": {
    "tab_ui": true,
    "iframe_tab": true
  }
}`}
                </pre>
              </div>
            </section>

            <section className="coreui-card-shell coreui-p-md extensions-schema-section">
              <div className="extensions-schema-section-header">
                <h4>Backend Provider (Python)</h4>
              </div>
              <div className="extensions-schema-section-body">
                <p>
                  The backend provider implements the extension logic. It should define a 
                  <code>create_provider(host_context, manifest)</code> function that returns an 
                  instance of your provider class.
                </p>
                <pre className="extensions-schema-diagnostics">
{`class MyExtension:
    def __init__(self, host_context, manifest):
        self._host = host_context
        self._manifest = manifest

    def get_tab_descriptor(self, **kwargs):
        return {
            "id": "my-tab",
            "title": "My Tab",
            "icon": "web_asset"
        }

    def get_tab_payload(self, **kwargs):
        return {
            "title": "My Tab",
            "content": {
                "type": "iframe",
                "src": "http://localhost:3000"
            }
        }`}
                </pre>
              </div>
            </section>

            <section className="coreui-card-shell coreui-p-md extensions-schema-section">
              <div className="extensions-schema-section-header">
                <h4>CoreUI Schemas</h4>
              </div>
              <div className="extensions-schema-section-body">
                <p>
                  Extensions can publish declarative UI schemas to render settings or status pages
                  directly in the CoreUI. Supported components include <code>status</code>, 
                  <code>text</code>, <code>table</code>, <code>input</code>, <code>select</code>, 
                  and <code>action</code>.
                </p>
                <pre className="extensions-schema-diagnostics">
{`"ui_schema": {
  "pages": [
    {
      "id": "overview",
      "title": "Overview",
      "sections": [
        {
          "id": "status-section",
          "title": "Status",
          "components": [
            { "type": "status", "key": "health", "label": "Health" }
          ]
        }
      ]
    }
  ]
}`}
                </pre>
              </div>
            </section>
          </>
        )}

        {subTab === "architecture" && (
          <div className="dashboard-tab">
            <section className="coreui-card-shell coreui-p-lg">
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
                      <h5>DockerManager</h5>
                      <p>Host Docker capability for extension service actions and Qdrant runtime operations. pip: <code>docker-manager</code></p>
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
            </section>
          </div>
        )}
      </div>
    </div>
  );
}
