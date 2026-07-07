import { useState, useEffect, useMemo } from 'react';
import CoreUISubtabs from './CoreUISubtabs';
import CoreUIModal from './CoreUIModal';
import CoreUIButton from './CoreUIButton';
import CoreUIPillTabs from './CoreUIPillTabs';
import { getLlmProxyStatus } from '../services/api';
import { t } from '../services/i18n.js';
import '../styles/components/DashboardTab.css';
import '../styles/components/SettingsTab.css';

const INFO_TAB_IDS = ['intro', 'features', 'quick-start', 'credits'];
const PROXY_KEY_MODAL_TAB_IDS = ['api-key', 'how-to-use'];

function DashboardTab({ onNavigate, onOpenLogs, onOpenLlmProxyAutocomplete, onOpenLlmProxySecurity }) {
  const [infoSubTab, setInfoSubTab] = useState('intro');
  const [showProxyKeyModal, setShowProxyKeyModal] = useState(false);
  const [proxyKeyModalTab, setProxyKeyModalTab] = useState('api-key');
  const [proxyStatus, setProxyStatus] = useState(null);
  const webuiOrigin = typeof window !== 'undefined' ? window.location.origin : 'the configured server URL';

  const infoTabs = useMemo(
    () => INFO_TAB_IDS.map((id) => ({ id, label: t(`dashboard.tab.${id}`) })),
    [],
  );
  const proxyKeyModalTabs = useMemo(
    () => PROXY_KEY_MODAL_TAB_IDS.map((id) => ({ id, label: t(`dashboard.proxy_modal.tab.${id}`) })),
    [],
  );

  useEffect(() => {
    if (showProxyKeyModal) {
      getLlmProxyStatus().then(setProxyStatus).catch(() => {});
    }
  }, [showProxyKeyModal]);

  const proxyBaseUrl = proxyStatus?.base_url || 'http://localhost:<port>';

  const go = (tabId) => {
    if (typeof onNavigate === 'function') onNavigate(tabId);
  };

  return (
    <div className="dashboard-tab tab-view">
      <div className="dashboard-layout">
        <section className="dashboard-info-card" aria-label={t('dashboard.about_aria')}>
          <div className="dashboard-info-card-header">
            <h2 className="dashboard-info-card-title">{t('app.title')}</h2>
            <p className="dashboard-info-card-subtitle">{t('app.subtitle')}</p>
          </div>
          <CoreUISubtabs
            tabs={infoTabs}
            value={infoSubTab}
            onChange={(id) => setInfoSubTab(id)}
            ariaLabel={t('dashboard.about_sections_aria')}
            className="dashboard-info-subtabs"
          />
          <div className="dashboard-info-panel" role="tabpanel">
            {infoSubTab === 'intro' && (
              <>
                <div className="dashboard-section-inner notice-section">
                  <div className="notice-content">
                    <h3>{t('dashboard.intro.tagline')}</h3>
                    <p>
                      <strong>{t('dashboard.intro.lead')}</strong>{' '}
                      {t('dashboard.intro.p1')}
                    </p>
                    <p>{t('dashboard.intro.p2')}</p>
                  </div>
                </div>
                <div className="dashboard-section-inner">
                  <h3>{t('dashboard.what_is.title')}</h3>
                  <p>{t('dashboard.what_is.p1')}</p>
                  <p>{t('dashboard.what_is.p2')}</p>
                  <button
                    type="button"
                    className="dashboard-primary-btn"
                    onClick={() => setShowProxyKeyModal(true)}
                  >
                    {t('dashboard.quick_start_btn')}
                  </button>
                </div>
              </>
            )}
            {infoSubTab === 'features' && (
              <div className="dashboard-section-inner">
                <h3>{t('dashboard.features.title')}</h3>
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
                    <p>LLM providers and Open WebUI run through service-owning extensions; Qdrant is managed by RagRuntime via DockerManager</p>
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
                    <p>8080 (main app) — auxiliary services on their own ports</p>
                  </div>
                </div>
              </div>
            )}
            {infoSubTab === 'quick-start' && (
              <div className="dashboard-section-inner">
                <h3>{t('dashboard.quick_start.title')}</h3>
                <p className="quick-start-intro">{t('dashboard.quick_start.intro')}</p>

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
                      <p>Start Qdrant through RagService and manage LLM providers/Open WebUI from their extension tabs:</p>
                      <code>python -m rag_service start-qdrant</code>
                      <p className="qs-hint">Docker Desktop and provider setup are explicit user-managed prerequisites; Docker service actions go through DockerManager.</p>
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
                      <code>python -m api.cli crawl</code>
                      <code>python -m api.cli ingest &lt;markdown_dir&gt;</code>
                      <p className="qs-hint">Monitor progress in the WebUI Crawler/Indexer tabs. Embeddings use the configured provider runtime.</p>
                    </div>
                  </div>

                  <div className="quick-start-card">
                    <div className="qs-number">5</div>
                    <div className="qs-content">
                      <h4>Launch WebUI</h4>
                      <p>Start the WebUI server and open in browser:</p>
                      <code>.\start_webui.bat</code>
                      <p className="qs-hint">Access at <code>{webuiOrigin}</code>. Use RAG tab to test queries.</p>
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
                        <strong>LLM Provider</strong>
                        <p>Extension-backed LLM provider runtime for chat, embeddings, and reranking.</p>
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
                <h3>{t('dashboard.credits.title')}</h3>
                <p className="credits-intro">{t('dashboard.credits.intro')}</p>

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
                      <h5>DockerManager</h5>
                      <p>Host Docker capability for service-owning extensions and Qdrant runtime operations.</p>
                      <code>pip: docker-manager</code>
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
                    <li><strong>LLM provider extensions</strong> — Provider runtimes for chat, embeddings, and reranking</li>
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

        <section className="dashboard-info-card dashboard-proxy-hint-card" aria-label={t('dashboard.proxy_card_aria')}>
          <div className="dashboard-info-card-header">
            <h2 className="dashboard-info-card-title">{t('dashboard.proxy_card.title')}</h2>
            <p className="dashboard-info-card-subtitle">{t('dashboard.proxy_card.subtitle')}</p>
          </div>
          <div className="dashboard-section-inner">
            <p className="dashboard-card-muted">{t('dashboard.proxy_card.body')}</p>
            <div className="dashboard-proxy-hint-actions">
              <button type="button" className="dashboard-text-btn" onClick={() => go('rag-fusion-proxy')}>
                {t('dashboard.proxy_card.open_proxy')}
              </button>
              {typeof onOpenLogs === 'function' && (
                <button type="button" className="dashboard-text-btn" onClick={() => onOpenLogs()}>
                  {t('dashboard.proxy_card.view_logs')}
                </button>
              )}
              {typeof onOpenLlmProxyAutocomplete === 'function' && (
                <button type="button" className="dashboard-text-btn" onClick={() => onOpenLlmProxyAutocomplete()}>
                  {t('dashboard.proxy_card.autocomplete')}
                </button>
              )}
            </div>
          </div>
        </section>
      </div>

      {showProxyKeyModal && (
        <CoreUIModal
          title={t('dashboard.proxy_modal.title')}
          className="proxy-api-key-modal"
          onClose={() => setShowProxyKeyModal(false)}
          footer={
            <CoreUIButton
              variant="primary"
              onClick={() => {
                setShowProxyKeyModal(false);
                typeof onOpenLlmProxySecurity === 'function' ? onOpenLlmProxySecurity() : go('tokens-security');
              }}
            >
              {t('dashboard.proxy_modal.open_generator')}
            </CoreUIButton>
          }
        >
          <div className="proxy-key-modal-tabs-wrapper">
            <CoreUIPillTabs
              tabs={proxyKeyModalTabs}
              value={proxyKeyModalTab}
              onChange={setProxyKeyModalTab}
              ariaLabel={t('dashboard.proxy_modal.sections_aria')}
            />
          </div>

          {proxyKeyModalTab === 'api-key' && (
            <div className="proxy-key-quick-start">
              <div className="proxy-how-to-card proxy-how-to-card--hero">
                <div className="proxy-how-to-card-header">
                  <span className="material-symbols-outlined">vpn_key</span>
                  <h3>Quick start</h3>
                </div>
                <p>
                  Create one WebUI-managed key before wiring IDEs, OpenWebUI, or other OpenAI-compatible clients to
                  Chiron <code>/v1</code> endpoints.
                </p>
              </div>

              <div className="proxy-how-to-card">
                <div className="proxy-how-to-card-header">
                  <span className="proxy-key-step-index">1</span>
                  <h3>Open Security</h3>
                </div>
                <p>
                  Open <strong>Tokens and Security</strong>, then use the <strong>Security</strong> card.
                </p>
              </div>

              <div className="proxy-how-to-card">
                <div className="proxy-how-to-card-header">
                  <span className="proxy-key-step-index">2</span>
                  <h3>Generate or reveal</h3>
                </div>
                <p>
                  Use <strong>Generate key</strong> for the first setup, <strong>Reveal key</strong> to copy it again,
                  or <strong>Regenerate key</strong> to rotate clients.
                </p>
              </div>

              <div className="proxy-how-to-card">
                <div className="proxy-how-to-card-header">
                  <span className="proxy-key-step-index">3</span>
                  <h3>Paste into client</h3>
                </div>
                <p>
                  Use the server base URL with the key as either <code>Authorization: Bearer &lt;key&gt;</code> or{' '}
                  <code>x-api-key: &lt;key&gt;</code> header.
                </p>
              </div>

              <div className="proxy-how-to-card proxy-how-to-card--note">
                <div className="proxy-how-to-card-header">
                  <span className="material-symbols-outlined">info</span>
                  <h3>Note</h3>
                </div>
                <p>
                  The protected surface is Chiron <code>/v1*</code>. Provider-native compatibility routes live in the
                  owning extensions.
                </p>
              </div>
            </div>
          )}

          {proxyKeyModalTab === 'how-to-use' && (
            <div className="proxy-key-how-to-use">
              <div className="proxy-how-to-card proxy-how-to-card--hero">
                <div className="proxy-how-to-card-header">
                  <span className="material-symbols-outlined">info</span>
                  <h3>Overview</h3>
                </div>
                <p>
                  This RAG proxy speaks <strong>OpenAI</strong> (<code>POST /v1/chat/completions</code>) and{' '}
                  <strong>Anthropic Messages</strong> (<code>POST /v1/messages</code>) over the same base URL, backed by the configured provider
                  and Qdrant.
                </p>
              </div>

              <div className="proxy-how-to-card">
                <div className="proxy-how-to-card-header">
                  <span className="material-symbols-outlined">link</span>
                  <h3>Base URL</h3>
                </div>
                <p>
                  Use <code>{proxyBaseUrl}</code> on the machine where this proxy runs
                  (or <code>http://&lt;PC_IP&gt;:&lt;port&gt;</code> from another device).
                </p>
              </div>

              <div className="proxy-how-to-card">
                <div className="proxy-how-to-card-header">
                  <span className="material-symbols-outlined">integration_instructions</span>
                  <h3>VSCode + Continue.dev</h3>
                </div>
                <p>
                  Configure an OpenAI-compatible provider, set the base URL to this
                  proxy, and use your <strong>build id</strong> as the model.
                </p>
              </div>

              <div className="proxy-how-to-card">
                <div className="proxy-how-to-card-header">
                  <span className="material-symbols-outlined">api</span>
                  <h3>Anthropic Messages</h3>
                </div>
                <p>
                  Set <code>ANTHROPIC_BASE_URL</code> to <code>{proxyBaseUrl}</code> (no path suffix),{' '}
                  <code>ANTHROPIC_API_KEY</code> empty, and <code>ANTHROPIC_AUTH_TOKEN</code> to your token policy.
                </p>
              </div>

              <div className="proxy-how-to-card">
                <div className="proxy-how-to-card-header">
                  <span className="material-symbols-outlined">settings</span>
                  <h3>Configuration</h3>
                </div>
                <p>
                  Set <code>model</code> to a <strong>build id</strong> from <strong>LLM Proxy</strong> (builds), or
                  a concrete provider model id for passthrough. Optional inline completions use logical id{' '}
                  <code>ChironAI-Autocomplete</code>.
                </p>
              </div>
            </div>
          )}
        </CoreUIModal>
      )}

    </div>
  );
}

export default DashboardTab;
