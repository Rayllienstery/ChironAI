import { useState } from "react";
import Card from "./Card";
import CoreUIBadge from "./CoreUIBadge";
import CoreUIButton from "./CoreUIButton";
import CoreUIDockerCard from "./CoreUIDockerCard";
import CoreUINotificationActionButton from "./CoreUINotificationActionButton";
import CoreUIPillTabs from "./CoreUIPillTabs";
import CoreUISubtabs from "./CoreUISubtabs";
import CoreUISlider from "./CoreUISlider";
import EmptyState from "./EmptyState";
import ExtensionRuntimeLoadingView, { buildExtensionRuntimeLoadingSteps } from "./ExtensionRuntimeLoadingView";
import StandByScreen from "./StandByScreen";
import "../styles/components/DockerTab.css";
import "../styles/components/DependenciesTab.css";
import "../styles/components/CoreUIShowcaseTab.css";
import CoreUIPipelinePreview from "./CoreUIPipelinePreview";

const sourceRoot = "src";

function CodePill({ children }) {
  return <code className="coreui-showcase-code-pill">{children}</code>;
}

function ShowcaseItem({ name, classes, source, description, children }) {
  return (
    <article className="coreui-showcase-item">
      <div className="coreui-showcase-preview">{children}</div>
      <div className="coreui-showcase-meta">
        <div>
          <span className="coreui-showcase-kicker">Internal name</span>
          <h3>{name}</h3>
        </div>
        <p>{description}</p>
        <div className="coreui-showcase-meta-row">
          <span>CSS</span>
          <div className="coreui-showcase-code-list">
            {classes.map((className) => (
              <CodePill key={className}>{className}</CodePill>
            ))}
          </div>
        </div>
        <div className="coreui-showcase-meta-row">
          <span>Source</span>
          <CodePill>{source}</CodePill>
        </div>
      </div>
    </article>
  );
}

function ShowcaseSection({ title, children }) {
  return (
    <section className="coreui-showcase-section" aria-labelledby={`coreui-showcase-${title.toLowerCase().replaceAll(" ", "-")}`}>
      <div className="coreui-showcase-section-header">
        <h2 id={`coreui-showcase-${title.toLowerCase().replaceAll(" ", "-")}`}>{title}</h2>
      </div>
      <div className="coreui-showcase-list">{children}</div>
    </section>
  );
}

function TokenSwatch({ label, token, className = "" }) {
  return (
    <div className={["coreui-showcase-token", className].filter(Boolean).join(" ")}>
      <span className="coreui-showcase-token-swatch" style={{ background: `var(${token})` }} />
      <span>{label}</span>
      <CodePill>{token}</CodePill>
    </div>
  );
}

function FontCard({ title, token, description, sampleClassName, sample }) {
  return (
    <article className="coreui-showcase-font-card">
      <h4>{title}</h4>
      <span className={["coreui-showcase-font-card-sample", sampleClassName].filter(Boolean).join(" ")}>
        {sample}
      </span>
      <p>{description}</p>
      <CodePill>{token}</CodePill>
    </article>
  );
}

const SHOWCASE_SUBTABS = [
  { id: "colors", label: "Colors and fonts" },
  { id: "buttons", label: "Buttons" },
  { id: "cards", label: "Cards" },
  { id: "components", label: "Components" },
  { id: "layout", label: "Layout & Navigation" },
  { id: "data", label: "Data & Feedback" },
  { id: "icons", label: "Icons" },
  { id: "notifications", label: "Notifications" },
];

function CoreUIShowcaseTab() {
  const [subtab, setSubtab] = useState("colors");

  return (
    <div className="coreui-showcase tab-view">
      <header className="coreui-showcase-hero">
        <div>
          <span className="coreui-showcase-kicker">Design system inventory</span>
          <h1>CoreUI Showcase</h1>
        </div>
        <p>
          Static catalog of reusable CoreUI primitives and common visual patterns.
        </p>
      </header>

      <CoreUIPillTabs
        tabs={SHOWCASE_SUBTABS}
        value={subtab}
        onChange={(id) => setSubtab(id)}
        ariaLabel="Showcase categories"
      />

      {subtab === "colors" && (
      <>
      <ShowcaseSection title="Fonts">
        <ShowcaseItem
          name="Font registry"
          classes={["--coreui-font-family-base", "--coreui-font-family-mono", "--coreui-font-family-icon"]}
          source={`${sourceRoot}/styles/tokens.css, index.html`}
          description="Approved CoreUI font list. Application UI, code-like surfaces, and icon ligatures should use only these registry tokens."
        >
          <div className="coreui-showcase-font-grid">
            <FontCard
              title="CoreUI Sans"
              token="--coreui-font-family-base"
              description="Default UI font stack for page text, headings, form controls, tables, and navigation labels."
              sampleClassName="coreui-showcase-font-card-sample--base"
              sample="Interface text Aa 123"
            />
            <FontCard
              title="CoreUI Mono"
              token="--coreui-font-family-mono"
              description="Single monospace stack for logs, code pills, IDs, model names, JSON, and technical diagnostics."
              sampleClassName="coreui-showcase-font-card-sample--mono"
              sample="trace_id=7f2c latency_ms=128"
            />
            <FontCard
              title="CoreUI Icons"
              token="--coreui-font-family-icon"
              description="Central icon ligature font for Material Symbols. Load stays in the CoreUI shell and components only consume the shared class."
              sampleClassName="coreui-showcase-font-card-sample--icon"
              sample={(
                <>
                  <span className="material-symbols-outlined" aria-hidden="true">dashboard</span>
                  <span className="material-symbols-outlined" aria-hidden="true">code</span>
                  <span className="material-symbols-outlined" aria-hidden="true">settings</span>
                </>
              )}
            />
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Typography scale"
          classes={["--md-sys-typescale-*"]}
          source={`${sourceRoot}/styles/tokens.css`}
          description="Shared Material-style type tokens for headings, labels, and body copy."
        >
          <div className="coreui-showcase-type-stack">
            <span className="coreui-showcase-type-headline">Headline medium</span>
            <span className="coreui-showcase-type-title">Title large</span>
            <span className="coreui-showcase-type-body">Body medium for dense application panels.</span>
            <span className="coreui-showcase-type-label">Label medium</span>
          </div>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="Colors">
        <ShowcaseItem
          name="Theme tokens"
          classes={[":root", ".theme-dark", "[data-accent-color]"]}
          source={`${sourceRoot}/styles/tokens.css`}
          description="Color, typography, spacing, elevation, radius, theme, and accent variables used across CoreUI."
        >
          <div className="coreui-showcase-token-grid">
            <TokenSwatch label="Primary" token="--md-sys-color-primary" />
            <TokenSwatch label="Surface" token="--md-sys-color-surface" />
            <TokenSwatch label="Container" token="--md-sys-color-surface-container" />
            <TokenSwatch label="Outline" token="--md-sys-color-outline-variant" />
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Semantic state tokens"
          classes={[
            "--coreui-color-success",
            "--coreui-color-warning",
            "--coreui-color-info",
            "--coreui-color-scrim",
          ]}
          source={`${sourceRoot}/styles/tokens.css`}
          description="Shared semantic tokens for success, warning, info, error-adjacent feedback, and overlay scrims."
        >
          <div className="coreui-showcase-token-grid">
            <TokenSwatch label="Success" token="--coreui-color-success-container" />
            <TokenSwatch label="Warning" token="--coreui-color-warning-container" />
            <TokenSwatch label="Info" token="--coreui-color-info-container" />
            <TokenSwatch label="Scrim" token="--coreui-color-scrim" className="coreui-showcase-token--scrim" />
          </div>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="Layout foundations">
        <ShowcaseItem
          name="Page width"
          classes={[".tab-view", ".coreui-page-shell", "--coreui-page-max-width"]}
          source={`${sourceRoot}/styles/tokens.css, ${sourceRoot}/styles/layout.css`}
          description="Standard content rail for all feature tabs. Root tab containers use .tab-view so pages share the 1280px Showcase width and center inside the app shell."
        >
          <div className="coreui-showcase-page-width-demo">
            <div className="coreui-showcase-page-width-rail">
              <CodePill>--coreui-page-max-width: 1280px</CodePill>
              <span>Centered tab content rail</span>
            </div>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Surface and elevation"
          classes={[".app-card", ".app-default-card", "--md-sys-elevation-level*"]}
          source={`${sourceRoot}/styles/layout.css, ${sourceRoot}/styles/default-card.css`}
          description="Standard raised surfaces for compact cards and larger tab sections."
        >
          <div className="coreui-showcase-surface-row">
            <Card className="coreui-showcase-demo-card">Card</Card>
            <section className="app-default-card coreui-showcase-demo-section">Default section</section>
          </div>
        </ShowcaseItem>
      </ShowcaseSection>
      </>
      )}

      {subtab === "buttons" && (
      <ShowcaseSection title="Buttons">
        <ShowcaseItem
          name="CoreUIButton"
          classes={[".coreui-btn", ".coreui-btn-primary", ".coreui-btn-danger", ".coreui-btn-ghost", ".coreui-btn-small", ".coreui-btn-icon"]}
          source={`${sourceRoot}/components/CoreUIButton.jsx`}
          description="Shared button primitive for toolbar, modal, and panel actions."
        >
          <div className="coreui-showcase-button-row">
            <CoreUIButton variant="primary">Primary</CoreUIButton>
            <CoreUIButton>Default</CoreUIButton>
            <CoreUIButton variant="danger">Danger</CoreUIButton>
            <CoreUIButton variant="ghost">Ghost</CoreUIButton>
            <CoreUIButton size="sm">Small</CoreUIButton>
            <CoreUIButton size="icon" aria-label="Icon button">
              <span className="material-symbols-outlined" aria-hidden="true">more_horiz</span>
            </CoreUIButton>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Action button groups"
          classes={["CoreUIButton", ".dashboard-primary-btn", ".dashboard-secondary-btn"]}
          source={`${sourceRoot}/components/CoreUIButton.jsx, ${sourceRoot}/styles/components/DashboardTab.css`}
          description="Standard replacement for the older capsule action buttons used by Dashboard, extensions, provider, and proxy screens."
        >
          <div className="coreui-showcase-action-button-stack">
            <div className="coreui-showcase-button-row">
              <CoreUIButton>Refresh</CoreUIButton>
              <CoreUIButton variant="primary">Stop service</CoreUIButton>
            </div>
            <div className="coreui-showcase-button-row">
              <CoreUIButton>Use LLM Proxy default</CoreUIButton>
              <CoreUIButton>Clear saved (env/default)</CoreUIButton>
            </div>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="CoreUINotificationActionButton"
          classes={[".coreui-notification-action-btn", ".coreui-notification-action-btn-icon", ".coreui-notification-action-btn-label"]}
          source={`${sourceRoot}/components/CoreUINotificationActionButton.jsx, ${sourceRoot}/styles/components/CoreUINotificationActionButton.css`}
          description="Pill-shaped card-as-button used by the floating notification center. Renders a Material icon plus an optional label, with level-3 elevation. Use the same component for the Bell toggle, the Clear action, and any other fixed overlay action."
        >
          <div className="coreui-showcase-button-row">
            <CoreUINotificationActionButton icon="notifications" label="Notifications" />
            <CoreUINotificationActionButton icon="cleaning_services" label="Clear" />
            <CoreUINotificationActionButton icon="notifications" />
          </div>
        </ShowcaseItem>
      </ShowcaseSection>
      )}

      {subtab === "cards" && (
      <>
      <ShowcaseSection title="Card anatomy">
        <ShowcaseItem
          name="Card structure"
          classes={[".app-card", ".app-card__header", ".app-card__body", ".app-card__footer", ".app-card-actions", "--md-sys-elevation-level1", "--md-sys-shape-corner-medium"]}
          source={`${sourceRoot}/components/Card.jsx, ${sourceRoot}/styles/layout.css, ${sourceRoot}/styles/tokens.css`}
          description="The default CoreUI card uses the surface color, a 16px medium corner radius, and Material 3 level-1 elevation. Use the slots below to place content: header (title + actions), body (the main payload), and footer (secondary actions or metadata)."
        >
          <Card className="coreui-showcase-card-anatomy">
            <header className="app-card__header">
              <div>
                <span className="coreui-showcase-kicker">Card header</span>
                <h3>Service status</h3>
              </div>
              <div className="app-card__header-actions">
                <CoreUIButton size="sm" variant="ghost">Refresh</CoreUIButton>
                <CoreUIButton size="sm" variant="primary">Restart</CoreUIButton>
              </div>
            </header>
            <div className="app-card__body">
              <span className="coreui-showcase-kicker">Card body</span>
              <p>Drop the main content here. Use <CodePill>app-card__body</CodePill> for padding, gaps, and rhythm. Headings, lists, metric grids, tables, and forms all live inside this slot.</p>
              <div className="coreui-meta-grid">
                <span><strong>Latency:</strong> 128 ms</span>
                <span><strong>Uptime:</strong> 14h 02m</span>
                <span><strong>Requests:</strong> 9 412</span>
              </div>
            </div>
            <footer className="app-card__footer">
              <span className="coreui-showcase-kicker">Card footer</span>
              <div className="coreui-card-actions">
                <CoreUIButton size="sm" variant="ghost">View logs</CoreUIButton>
                <CoreUIButton size="sm" variant="ghost">Open dashboard</CoreUIButton>
              </div>
              <span className="coreui-showcase-kicker">Updated 2 min ago</span>
            </footer>
          </Card>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="Card variants">
        <ShowcaseItem
          name="Card"
          classes={[".app-card", ".app-card--interactive", ".app-card--elevate-on-hover"]}
          source={`${sourceRoot}/components/Card.jsx, ${sourceRoot}/styles/layout.css, ${sourceRoot}/styles/tokens.css`}
          description="Compact elevated surface. Hoverable cards keep a neutral surface and signal interaction with a denser accent-colored shadow."
        >
          <div className="coreui-showcase-card-variants">
            <Card className="coreui-showcase-demo-card">Default card</Card>
            <Card interactive className="coreui-showcase-demo-card">
              Interactive (cursor)
            </Card>
            <Card interactive elevateOnHover className="coreui-showcase-demo-card">
              Hover me ↑
            </Card>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Main card patterns"
          classes={[".app-card", ".app-default-card", ".coreui-card-shell", ".coreui-card-shell--raised", ".coreui-panel-note"]}
          source={`${sourceRoot}/components/Card.jsx, ${sourceRoot}/styles/default-card.css, ${sourceRoot}/styles/coreui-system.css`}
          description="Approved surface hierarchy: compact card, full section card, raised utility card, and semantic note panel."
        >
          <div className="coreui-showcase-card-grid">
            <Card className="coreui-showcase-demo-card">Compact app card</Card>
            <section className="app-default-card coreui-showcase-demo-section">Primary section card</section>
            <section className="coreui-card-shell coreui-p-md">Utility shell card</section>
            <section className="coreui-card-shell coreui-card-shell--raised coreui-p-md">Raised emphasis card</section>
            <section className="coreui-panel-note coreui-panel-note--info">Semantic note card</section>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Model card (provider pattern)"
          classes={[".app-card", ".app-card--interactive", ".app-card--elevate-on-hover", ".extensions-runtime-model-card"]}
          source={`${sourceRoot}/components/Card.jsx, ${sourceRoot}/styles/components/ExtensionRuntimeTab.css`}
          description="Model card used in provider runtime tabs. It follows the CoreUI hoverable-card rule: neutral body, stronger accent-tinted hover shadow."
        >
          <div className="coreui-showcase-model-card-grid">
            <Card interactive elevateOnHover className="extensions-runtime-model-card">
              <div className="extensions-runtime-model-card__top">
                <div className="extensions-runtime-model-card__title-wrap">
                  <div className="extensions-runtime-model-card__title">qwen2.5-coder:7b</div>
                </div>
              </div>
              <div className="extensions-runtime-model-card__provider">
                <span className="extensions-runtime-model-meta-k">Provider:</span>
                <div className="extensions-runtime-model-provider-val">
                  <span className="extensions-runtime-model-meta-v">qwen</span>
                </div>
              </div>
              <div className="extensions-runtime-model-card__meta">
                <div className="extensions-runtime-model-meta-row">
                  <span className="extensions-runtime-model-meta-k">Size:</span>
                  <span className="extensions-runtime-model-meta-v">4.73 GB</span>
                </div>
                <div className="extensions-runtime-model-meta-row">
                  <span className="extensions-runtime-model-meta-k">Modified:</span>
                  <span className="extensions-runtime-model-meta-v">2026-04-28</span>
                </div>
              </div>
            </Card>
            <Card interactive elevateOnHover className="extensions-runtime-model-card">
              <div className="extensions-runtime-model-card__top">
                <div className="extensions-runtime-model-card__title-wrap">
                  <div className="extensions-runtime-model-card__title">llama3.2:3b</div>
                </div>
              </div>
              <div className="extensions-runtime-model-card__provider">
                <span className="extensions-runtime-model-meta-k">Provider:</span>
                <div className="extensions-runtime-model-provider-val">
                  <span className="extensions-runtime-model-meta-v">meta</span>
                </div>
              </div>
              <div className="extensions-runtime-model-card__meta">
                <div className="extensions-runtime-model-meta-row">
                  <span className="extensions-runtime-model-meta-k">Size:</span>
                  <span className="extensions-runtime-model-meta-v">2.01 GB</span>
                </div>
                <div className="extensions-runtime-model-meta-row">
                  <span className="extensions-runtime-model-meta-k">Modified:</span>
                  <span className="extensions-runtime-model-meta-v">2026-04-25</span>
                </div>
              </div>
            </Card>
          </div>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="Runtime cards">
        <ShowcaseItem
          name="Docker card"
          classes={[".coreui-docker-card", ".coreui-docker-card__header", ".coreui-docker-card__body", ".coreui-docker-card__primary", ".coreui-docker-card__meta-grid", ".coreui-docker-card__meta-cell", ".coreui-docker-card__actions", ".coreui-docker-card__field", "--md-sys-shape-corner-medium", "--md-sys-elevation-level1"]}
          source={`${sourceRoot}/components/CoreUIDockerCard.jsx, ${sourceRoot}/styles/components/CoreUIDockerCard.css, ${sourceRoot}/styles/tokens.css`}
          description="Standardized runtime card for Docker-managed services. Header shows the runtime name, description, and a status badge (with optional HTTP code). Body is a two-column layout: a primary column with the chat backend URL field and an action row (Refresh, Apply, Stop, Clear, Open external), and a secondary column with metadata tiles (Container, Image, Status, Image version, Host URL, Port, Backend source, Chiron OpenAI URL, Chiron API key). Built on Card, CoreUIBadge, and CoreUIButton primitives; uses Material 3 tokens for color, radius, and elevation."
        >
          <CoreUIDockerCard
            name="Open WebUI"
            description="Docker-managed Open WebUI runtime"
            icon="deployed_code"
            status={{ tone: "success", label: "running" }}
            httpStatus="HTTP 200"
            backendUrl="http://host.docker.internal:8080"
            backendUrlLabel="Chat backend URL"
            actions={[
              { label: "Refresh", icon: "refresh" },
              { label: "Apply configuration", variant: "primary" },
              { label: "Stop service", variant: "danger", icon: "stop_circle" },
              { label: "Clear saved backend", variant: "ghost" },
              { label: "Open external", icon: "open_in_new" },
            ]}
            meta={[
              { label: "Container", value: "open-webui" },
              { label: "Image", value: "ghcr.io/open-webui/open-webui:main" },
              { label: "Status", value: { tone: "success", label: "running" } },
              { label: "Image version", value: { tone: "success", label: "up_to_date" } },
              { label: "Host URL", value: "http://localhost:3000" },
              { label: "Port", value: "3000:8080" },
              { label: "Backend source", value: "saved" },
              { label: "Chiron OpenAI URL", value: "http://host.docker.internal:8080/v1" },
              { label: "Chiron API key", value: "recoverable" },
            ]}
          />
        </ShowcaseItem>

        <ShowcaseItem
          name="Docker card — minimal state"
          classes={[".coreui-docker-card", ".coreui-docker-card__meta-value-empty"]}
          source={`${sourceRoot}/components/CoreUIDockerCard.jsx, ${sourceRoot}/styles/components/CoreUIDockerCard.css`}
          description="Same layout rendered with a stopped status, an empty backend URL, and empty metadata tiles. The component degrades gracefully: missing values render an em-dash placeholder and a non-running status badge tone."
        >
          <CoreUIDockerCard
            name="Open WebUI"
            description="Docker-managed Open WebUI runtime"
            icon="deployed_code"
            status={{ tone: "error", label: "stopped" }}
            backendUrl=""
            actions={[
              { label: "Refresh", icon: "refresh" },
              { label: "Start service", variant: "primary", icon: "play_circle" },
            ]}
            meta={[
              { label: "Container", value: "" },
              { label: "Image", value: "" },
              { label: "Status", value: { tone: "error", label: "stopped" } },
              { label: "Image version", value: { tone: "warning", label: "not checked" } },
              { label: "Host URL", value: "" },
              { label: "Port", value: "" },
              { label: "Backend source", value: "" },
              { label: "Chiron OpenAI URL", value: "" },
              { label: "Chiron API key", value: "" },
            ]}
          />
        </ShowcaseItem>
      </ShowcaseSection>
      </>
      )}

      {subtab === "components" && (
      <ShowcaseSection title="Core Components">
        <ShowcaseItem
          name="CoreUIButton"
          classes={[".coreui-btn", ".coreui-btn-primary", ".coreui-btn-danger", ".coreui-btn-ghost", ".coreui-btn-small", ".coreui-btn-icon"]}
          source={`${sourceRoot}/components/CoreUIButton.jsx`}
          description="Shared button primitive for toolbar, modal, and panel actions."
        >
          <div className="coreui-showcase-button-row">
            <CoreUIButton variant="primary">Primary</CoreUIButton>
            <CoreUIButton>Default</CoreUIButton>
            <CoreUIButton variant="danger">Danger</CoreUIButton>
            <CoreUIButton variant="ghost">Ghost</CoreUIButton>
            <CoreUIButton size="sm">Small</CoreUIButton>
            <CoreUIButton size="icon" aria-label="Icon button">
              <span className="material-symbols-outlined" aria-hidden="true">more_horiz</span>
            </CoreUIButton>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Action button groups"
          classes={["CoreUIButton", ".dashboard-primary-btn", ".dashboard-secondary-btn"]}
          source={`${sourceRoot}/components/CoreUIButton.jsx, ${sourceRoot}/styles/components/DashboardTab.css`}
          description="Standard replacement for the older capsule action buttons used by Dashboard, extensions, provider, and proxy screens."
        >
          <div className="coreui-showcase-action-button-stack">
            <div className="coreui-showcase-button-row">
              <CoreUIButton>Refresh</CoreUIButton>
              <CoreUIButton variant="primary">Stop service</CoreUIButton>
            </div>
            <div className="coreui-showcase-button-row">
              <CoreUIButton>Use LLM Proxy default</CoreUIButton>
              <CoreUIButton>Clear saved (env/default)</CoreUIButton>
            </div>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="EmptyState"
          classes={[".coreui-empty-state"]}
          source={`${sourceRoot}/components/EmptyState.jsx`}
          description="Dashed neutral panel for missing data, unavailable integrations, and empty results."
        >
          <EmptyState>No records available for this filter.</EmptyState>
        </ShowcaseItem>

        <ShowcaseItem
          name="CoreUIPipelinePreview"
          classes={[".coreui-pipeline-preview", ".coreui-pipeline-preview--animated", ".coreui-pipeline-preview__item"]}
          source={`${sourceRoot}/components/CoreUIPipelinePreview.jsx`}
          description="Standardized vertical pipeline diagram for request flows, build steps, and multi-stage processes. Supports staggered entrance animations."
        >
          <div style={{ maxWidth: '400px' }}>
            <div style={{ marginBottom: '16px', display: 'flex', gap: '8px', alignItems: 'center' }}>
              <button 
                className="rag-button primary" 
                onClick={() => {
                  const el = document.getElementById('showcase-pipeline-demo');
                  if (el) {
                    const clone = el.cloneNode(true);
                    el.parentNode.replaceChild(clone, el);
                  }
                }}
              >
                Replay Animation
              </button>
              <span style={{ fontSize: '12px', color: 'var(--md-sys-color-outline)' }}>
                Uses <code>animated</code> prop + <code>key</code> trigger
              </span>
            </div>
            <div id="showcase-pipeline-demo">
              <CoreUIPipelinePreview
                animated
                steps={[
                  { id: '1', label: 'Parse request', description: 'Read messages, model, and tools from OpenAI/Anthropic body.', icon: 'login', active: true, tone: 'success' },
                  { id: '2', label: 'RAG gate', description: 'Compute trigger score and decide if vector search is needed.', icon: 'gate', active: true, tone: 'success' },
                  { id: '3', label: 'Retrieval', description: 'Search Qdrant with dense/sparse vectors and hybrid fusion.', icon: 'database', active: true, tone: 'success' },
                  { id: '4', label: 'Rank & Rerank', description: 'Sort by priority and optional LLM rerank on candidates.', icon: 'swap_vert', active: true, tone: 'info', badges: ['Rerank On'] },
                  { id: '5', label: 'LLM call', description: 'Send assembled prompt to the provider for final completion.', icon: 'smart_toy', active: true, tone: 'success' },
                ]}
              />
            </div>
          </div>
        </ShowcaseItem>
      </ShowcaseSection>
      )}

      {subtab === "layout" && (
      <>
      <ShowcaseSection title="Navigation & Status">
        <ShowcaseItem
          name="Sidebar navigation row"
          classes={[".coreui-sidebar__link", ".coreui-sidebar__link--active", ".coreui-sidebar__icon"]}
          source={`${sourceRoot}/components/SidebarNav.jsx`}
          description="Left navigation link pattern with Material Symbol icon, active state, and label."
        >
          <div className="coreui-showcase-nav-demo">
            <button type="button" className="coreui-showcase-nav-row coreui-showcase-nav-row-active">
              <span className="material-symbols-outlined" aria-hidden="true">widgets</span>
              <span>CoreUI Showcase</span>
            </button>
            <button type="button" className="coreui-showcase-nav-row">
              <span className="material-symbols-outlined" aria-hidden="true">article</span>
              <span>Logs</span>
            </button>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Service status"
          classes={[".status-pill", ".status-dot", ".status-spinner", ".status-text"]}
          source={`${sourceRoot}/styles/layout.css`}
          description="Compact status indicators for reachable, stopped, and polling service states."
        >
          <div className="coreui-showcase-status-row">
            <span className="status-pill">
              <span className="status-dot running" />
              <span className="status-label">RAG</span>
              <span className="status-text">running</span>
            </span>
            <span className="status-pill">
              <span className="status-dot stopped" />
              <span className="status-label">Provider</span>
              <span className="status-text">stopped</span>
            </span>
            <span className="status-text-updating">
              <span className="status-spinner" />
              checking
            </span>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="StandByScreen"
          classes={[".standby-screen", ".standby-card", ".standby-loading-indicator", ".standby-loading-shape", ".standby-progress", ".standby-progress-meta", ".standby-module-name"]}
          source={`${sourceRoot}/components/StandByScreen.jsx, ${sourceRoot}/styles/components/StandByScreen.css`}
          description="Shared ChironAI stand-by loading view with a Material 3 tonal container, uncontained morphing loading indicator, indeterminate progress bar, and current module label."
        >
          <div className="coreui-showcase-standby-row">
            <StandByScreen moduleName="Session Manager" size="md" />
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="ExtensionRuntimeLoadingView"
          classes={[
            ".extensions-runtime-loading-shell",
            ".extensions-runtime-loading-card",
            ".extensions-runtime-loading-step",
            ".extensions-runtime-loading-step-chip",
          ]}
          source={`${sourceRoot}/components/ExtensionRuntimeLoadingView.jsx, ${sourceRoot}/styles/components/ExtensionRuntimeTab.css`}
          description="Extension tab loading surface for the two-phase manifest/cache loader, including active refresh, stale cache, and timeout states."
        >
          <div className="coreui-showcase-extension-loading-demo">
            <ExtensionRuntimeLoadingView
              title="Ollama"
              extensionId="ollama-provider"
              elapsedMs={7300}
              steps={buildExtensionRuntimeLoadingSteps({
                endpoint: "/api/webui/extensions/ollama-provider/tab",
                loadState: {
                  status: "refreshing",
                  job_id: "tab-a13f7c92",
                  phases: { descriptor: "ready", payload: "refreshing" },
                },
                message: "Inspecting Docker container and provider runtime.",
                mode: "payload",
              })}
            />
            <ExtensionRuntimeLoadingView
              title="Open WebUI"
              extensionId="open-webui"
              elapsedMs={12400}
              steps={buildExtensionRuntimeLoadingSteps({
                endpoint: "/api/webui/extensions/open-webui/tab",
                loadState: {
                  status: "stale",
                  job_id: "tab-stale",
                  phases: { descriptor: "ready", payload: "ready" },
                },
                message: "Showing cached payload while refreshing provider status.",
              })}
            />
            <ExtensionRuntimeLoadingView
              title="Codex"
              extensionId="codex-launcher"
              elapsedMs={6100}
              steps={buildExtensionRuntimeLoadingSteps({
                endpoint: "/api/webui/extensions/codex-launcher/tab",
                loadState: {
                  status: "timeout",
                  job_id: "tab-timeout",
                  error: "Provider payload timed out after 5.0s",
                  phases: { descriptor: "ready", payload: "timeout" },
                },
                message: "Provider payload timed out after 5.0s",
              })}
            />
          </div>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="Forms & Controls">
        <ShowcaseItem
          name="Text fields"
          classes={[".coreui-form-field", ".coreui-input", ".coreui-textarea", ".coreui-field-hint"]}
          source={`${sourceRoot}/styles/coreui-system.css`}
          description="Approved form field contract for settings screens, editors, and setup wizards."
        >
          <div className="coreui-showcase-form-grid">
            <label className="coreui-form-field">
              <span>Model name</span>
              <input className="coreui-input" value="qwen2.5-coder" readOnly />
              <span className="coreui-field-hint">Saved as the API-visible model id.</span>
            </label>
            <label className="coreui-form-field">
              <span>Prompt note</span>
              <textarea className="coreui-textarea" value="Reusable form surface." readOnly />
              <span className="coreui-field-hint">Uses the same contract in modal and page forms.</span>
            </label>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Select and boolean controls"
          classes={[".coreui-select", ".coreui-checkbox", ".coreui-switch"]}
          source={`${sourceRoot}/styles/coreui-system.css`}
          description="Unified select, checkbox, and switch patterns for settings and wizard-style screens."
        >
          <div className="coreui-showcase-control-row">
            <label className="coreui-form-field coreui-showcase-select-field">
              <span>Mode</span>
              <select className="coreui-select" value="system" onChange={() => {}} aria-label="Mode preview">
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            <label className="coreui-checkbox">
              <input type="checkbox" checked readOnly />
              <span>Enabled</span>
            </label>
            <label className="coreui-switch">
              <input type="checkbox" checked readOnly />
              <span aria-hidden="true" />
              <strong>Live</strong>
            </label>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="CoreUISlider"
          classes={[".coreui-slider-field", ".coreui-slider-title", ".coreui-slider"]}
          source={`${sourceRoot}/components/CoreUISlider.jsx`}
          description="Shared range control with a compact title row and current value for model settings and numeric tuning."
        >
          <div className="coreui-showcase-slider-row">
            <CoreUISlider
              label="Temperature"
              valueText="0.7"
              min="0"
              max="2"
              step="0.1"
              value="0.7"
              onChange={() => {}}
              aria-label="Showcase temperature"
            />
            <CoreUISlider
              label="Top K"
              valueText="12"
              min="1"
              max="30"
              step="1"
              value="12"
              onChange={() => {}}
              aria-label="Showcase top k"
            />
          </div>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="Layout Utilities">
        <ShowcaseItem
          name="Layout and utility patterns"
          classes={[".coreui-card-actions", ".coreui-inline-cluster", ".coreui-stack-sm", ".coreui-meta-grid"]}
          source={`${sourceRoot}/styles/coreui-system.css`}
          description="Reusable layout helpers for action rows, compact stacks, metadata chips, and dense panel composition."
        >
          <div className="coreui-showcase-utility-stack">
            <div className="coreui-card-actions">
              <CoreUIButton>Refresh</CoreUIButton>
              <CoreUIButton variant="primary">Save</CoreUIButton>
            </div>
            <div className="coreui-meta-grid">
              <span><strong>Model:</strong> qwen2.5-coder</span>
              <span><strong>Latency:</strong> 128 ms</span>
              <span><strong>Tokens:</strong> 912</span>
            </div>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Spacing and margins"
          classes={[".coreui-gap-*", ".coreui-mt-*", ".coreui-mb-*", ".coreui-p-*", ".coreui-section-block"]}
          source={`${sourceRoot}/styles/coreui-system.css`}
          description="Approved spacing utilities for margins, internal padding, section rhythm, and compact layout composition."
        >
          <div className="coreui-showcase-spacing-demo">
            <div className="coreui-card-shell coreui-p-md coreui-stack-sm">
              <div className="coreui-showcase-spacing-row">
                <CodePill>.coreui-p-md</CodePill>
                <span>Use on cards and note panels for default inner padding.</span>
              </div>
              <div className="coreui-showcase-spacing-row coreui-mt-sm">
                <CodePill>.coreui-mt-sm</CodePill>
                <span>Use for a small top separation between related controls.</span>
              </div>
              <div className="coreui-showcase-spacing-row coreui-mb-md">
                <CodePill>.coreui-mb-md</CodePill>
                <span>Use under headings or alert blocks before the next section.</span>
              </div>
              <div className="coreui-inline-cluster coreui-gap-md">
                <CodePill>.coreui-inline-cluster</CodePill>
                <CodePill>.coreui-gap-md</CodePill>
                <span>Use for action rows and metadata groups.</span>
              </div>
              <div className="coreui-section-block">
                <CodePill>.coreui-section-block</CodePill>
                <span>Use to separate stacked content blocks with default vertical rhythm.</span>
              </div>
            </div>
          </div>
        </ShowcaseItem>
      </ShowcaseSection>
      <ShowcaseSection title="Tab Selector">
        <ShowcaseItem
          name="CoreUIPillTabs"
          classes={[".coreui-pill-tablist", ".coreui-pill-tab", ".coreui-pill-tab-active"]}
          source={`${sourceRoot}/components/CoreUIPillTabs.jsx`}
          description="Reusable horizontal segmented navigation for primary tabs, section tabs, and mode switchers that sit outside cards."
        >
          <CoreUIPillTabs
            tabs={[
              { id: "overview", label: "Overview" },
              { id: "traces", label: "Traces" },
              { id: "settings", label: "Settings" },
            ]}
            value="traces"
            ariaLabel="Showcase tabs preview"
          />
        </ShowcaseItem>

        <ShowcaseItem
          name="CoreUISubtabs"
          classes={[".coreui-subtabs", ".coreui-subtab", ".coreui-subtab-active"]}
          source={`${sourceRoot}/components/CoreUISubtabs.jsx`}
          description="Secondary/subtab navigation with a bottom border and tinted active state. Use for in-card sections, panels, and compact informational guides."
        >
          <CoreUISubtabs
            tabs={[
              { id: "intro", label: "Intro" },
              { id: "features", label: "Features" },
              { id: "architecture", label: "Architecture" },
            ]}
            value="features"
            ariaLabel="Showcase subtabs preview"
          />
        </ShowcaseItem>
      </ShowcaseSection>
      </>
      )}

      {subtab === "data" && (
      <>
      <ShowcaseSection title="Docker Manager Views">
        <ShowcaseItem
          name="Docker status panel"
          classes={[".docker-status-panel", ".docker-status-main", ".docker-status-grid"]}
          source={`${sourceRoot}/components/DockerTab.jsx, ${sourceRoot}/styles/components/DockerTab.css`}
          description="Generic Docker Engine status surface for CLI availability, server readiness, and local runtime counts."
        >
          <section className="app-default-card docker-status-panel coreui-showcase-docker-status" aria-label="Docker status preview">
            <div className="docker-status-main">
              <CoreUIBadge tone="success">Engine ready</CoreUIBadge>
              <div>
                <strong>docker</strong>
                <span>Docker CLI and Engine status loaded.</span>
              </div>
            </div>
            <div className="docker-status-grid">
              <div>
                <span>CLI</span>
                <strong>26.1.4</strong>
              </div>
              <div>
                <span>Server</span>
                <strong>26.1.4</strong>
              </div>
              <div>
                <span>Containers</span>
                <strong>2</strong>
              </div>
              <div>
                <span>Images</span>
                <strong>5</strong>
              </div>
            </div>
          </section>
        </ShowcaseItem>

        <ShowcaseItem
          name="Docker containers table"
          classes={[".docker-section", ".docker-table-wrap", ".docker-table", ".docker-action-row"]}
          source={`${sourceRoot}/components/DockerTab.jsx, ${sourceRoot}/styles/components/DockerTab.css`}
          description="Operator table for generic containers with start, stop, and remove actions guarded by caller-side confirmation."
        >
          <section className="app-default-card docker-section coreui-showcase-docker-panel" aria-label="Docker containers preview">
            <div className="docker-section__header">
              <h3>Containers</h3>
              <CoreUIBadge tone="info">2 total</CoreUIBadge>
            </div>
            <div className="docker-table-wrap">
              <table className="docker-table coreui-showcase-docker-table">
                <thead>
                  <tr>
                    <th>Name</th>
                    <th>Image</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>
                      <strong>my-extension-service</strong>
                      <span>7f2c1b9a0d42</span>
                    </td>
                    <td>ghcr.io/acme/service:latest</td>
                    <td><CoreUIBadge tone="success">running</CoreUIBadge></td>
                    <td>
                      <div className="docker-action-row">
                        <CoreUIButton size="sm" variant="ghost">
                          <span className="material-symbols-outlined" aria-hidden="true">stop_circle</span>
                          Stop
                        </CoreUIButton>
                        <CoreUIButton size="sm" variant="danger">
                          <span className="material-symbols-outlined" aria-hidden="true">delete</span>
                          Remove
                        </CoreUIButton>
                      </div>
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <strong>worker-cache</strong>
                      <span>9ac0440e731b</span>
                    </td>
                    <td>registry.example.local/cache:stable</td>
                    <td><CoreUIBadge>exited</CoreUIBadge></td>
                    <td>
                      <div className="docker-action-row">
                        <CoreUIButton size="sm" variant="ghost">
                          <span className="material-symbols-outlined" aria-hidden="true">play_circle</span>
                          Start
                        </CoreUIButton>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </ShowcaseItem>

        <ShowcaseItem
          name="Docker images table"
          classes={[".docker-section", ".docker-table", ".docker-action-row", ".docker-message"]}
          source={`${sourceRoot}/components/DockerTab.jsx, ${sourceRoot}/styles/components/DockerTab.css`}
          description="Local image inventory with best-effort update state and image-level check, update, and remove actions."
        >
          <section className="app-default-card docker-section coreui-showcase-docker-panel" aria-label="Docker images preview">
            <div className="docker-section__header">
              <h3>Images</h3>
              <CoreUIBadge tone="info">2 local</CoreUIBadge>
            </div>
            <div className="docker-message docker-message--info">Checked ghcr.io/acme/service:latest</div>
            <div className="docker-table-wrap">
              <table className="docker-table coreui-showcase-docker-table">
                <thead>
                  <tr>
                    <th>Image</th>
                    <th>ID</th>
                    <th>Update</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td>
                      <strong>ghcr.io/acme/service:latest</strong>
                      <span>ghcr.io/acme/service</span>
                    </td>
                    <td>0f2a92ce88b4</td>
                    <td><CoreUIBadge tone="warning">update_available</CoreUIBadge></td>
                    <td>
                      <div className="docker-action-row">
                        <CoreUIButton size="sm" variant="ghost">
                          <span className="material-symbols-outlined" aria-hidden="true">published_with_changes</span>
                          Check
                        </CoreUIButton>
                        <CoreUIButton size="sm" variant="ghost">
                          <span className="material-symbols-outlined" aria-hidden="true">system_update_alt</span>
                          Update
                        </CoreUIButton>
                      </div>
                    </td>
                  </tr>
                  <tr>
                    <td>
                      <strong>registry.example.local/cache:stable</strong>
                      <span>registry.example.local/cache</span>
                    </td>
                    <td>19b33fd117ac</td>
                    <td><CoreUIBadge tone="success">up_to_date</CoreUIBadge></td>
                    <td>
                      <div className="docker-action-row">
                        <CoreUIButton size="sm" variant="danger">
                          <span className="material-symbols-outlined" aria-hidden="true">delete</span>
                          Remove
                        </CoreUIButton>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </section>
        </ShowcaseItem>

        <ShowcaseItem
          name="Docker contracts guide"
          classes={[".docker-contracts", ".docker-contract-grid", ".docker-contract-block"]}
          source={`${sourceRoot}/components/DockerTab.jsx, ${sourceRoot}/styles/components/DockerTab.css`}
          description="Developer-facing contract docs for extension backends that use host_context.docker_runtime instead of WebUI routes."
        >
          <section className="app-default-card docker-section docker-contracts coreui-showcase-docker-panel" aria-label="Docker contracts preview">
            <div className="docker-section__header">
              <h3>Extension Contract</h3>
              <CoreUIBadge tone="info">CoreModule API</CoreUIBadge>
            </div>
            <div className="docker-contract-grid coreui-showcase-docker-contract-grid">
              <article className="docker-contract-block">
                <h4>Host capability</h4>
                <p>Extensions receive DockerManager through <code>host_context.docker_runtime</code>.</p>
                <pre>{`def create_provider(host_context, manifest):
    return MyProvider(host_context, manifest)`}</pre>
              </article>
              <article className="docker-contract-block">
                <h4>Lifecycle</h4>
                <p>Use <code>DockerContainerSpec</code> and let <code>ensure_container</code> own create/start/recreate.</p>
                <pre>{`spec = DockerContainerSpec(
    name="my-extension-service",
    image="ghcr.io/acme/service:latest",
)
return docker.ensure_container(spec)`}</pre>
              </article>
            </div>
          </section>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="Data & Feedback Patterns">
        <ShowcaseItem
          name="Metric card"
          classes={[".metric-card", ".metric-label", ".metric-value"]}
          source={`${sourceRoot}/styles/layout.css`}
          description="Small dashboard telemetry surface for dense status readouts."
        >
          <Card className="metric-card">
            <span className="metric-label">GPU util</span>
            <span className="metric-value">42%</span>
          </Card>
        </ShowcaseItem>

        <ShowcaseItem
          name="Dense data row"
          classes={[".coreui-showcase-data-table", ".coreui-showcase-data-row"]}
          source={`${sourceRoot}/styles/components/CoreUIShowcaseTab.css`}
          description="Scannable table/list pattern for logs, traces, model lists, and run summaries."
        >
          <div className="coreui-showcase-data-table" role="table" aria-label="Data row preview">
            <div className="coreui-showcase-data-row" role="row">
              <span role="cell">rag.retrieval</span>
              <span role="cell">128 ms</span>
              <span role="cell"><CoreUIBadge>cached</CoreUIBadge></span>
            </div>
            <div className="coreui-showcase-data-row" role="row">
              <span role="cell">proxy.trace</span>
              <span role="cell">2.4 s</span>
              <span role="cell"><CoreUIBadge tone="warning">slow</CoreUIBadge></span>
            </div>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Dependency update panel"
          classes={[".dependencies-update-panel", ".dependencies-job-orb", ".dependencies-update-row"]}
          source={`${sourceRoot}/components/DependenciesTab.jsx, ${sourceRoot}/styles/components/DependenciesTab.css`}
          description="Operational status surface for dependency inventory, update checks, and package-manager job output."
        >
          <div className="coreui-showcase-dependencies-preview">
            <div className="dependencies-update-panel">
              <div className="dependencies-update-main">
                <div className="dependencies-job-orb dependencies-job-orb--running">
                  <span className="material-symbols-outlined" aria-hidden="true">progress_activity</span>
                </div>
                <div>
                  <h2>Checking updates</h2>
                  <p>running - 1 step - Jun 3, 14:20</p>
                </div>
              </div>
              <div className="dependencies-update-meta">
                <CoreUIBadge tone="info">running</CoreUIBadge>
              </div>
            </div>
            <div className="dependencies-update-row">
              <span className="material-symbols-outlined" aria-hidden="true">deployed_code</span>
              <strong>vite</strong>
              <span>5.0.8</span>
              <span className="material-symbols-outlined dependencies-update-arrow" aria-hidden="true">arrow_forward</span>
              <span>5.4.0</span>
            </div>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Feedback badges"
          classes={[".coreui-badge", ".coreui-badge--success", ".coreui-badge--warning", ".coreui-badge--error", ".coreui-badge--info"]}
          source={`${sourceRoot}/components/CoreUIBadge.jsx, ${sourceRoot}/styles/coreui-system.css`}
          description="Shared badge and status pill semantics for inline state display."
        >
          <div className="coreui-showcase-feedback-row">
            <CoreUIBadge>neutral</CoreUIBadge>
            <CoreUIBadge tone="success">success</CoreUIBadge>
            <CoreUIBadge tone="warning">warning</CoreUIBadge>
            <CoreUIBadge tone="error">error</CoreUIBadge>
            <CoreUIBadge tone="info">info</CoreUIBadge>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Code and JSON surfaces"
          classes={[".coreui-mono-block", ".coreui-text-muted-sm", ".coreui-text-break"]}
          source={`${sourceRoot}/styles/coreui-system.css`}
          description="Approved mono surface for logs, request snapshots, trace payloads, and diagnostics."
        >
          <div className="coreui-showcase-mono-stack">
            <pre className="coreui-mono-block">{`{\n  "trace_id": "7f2c1b9a",\n  "latency_ms": 128,\n  "status": "ok"\n}`}</pre>
            <p className="coreui-text-muted-sm">Use for JSON, logs, request snapshots, and diagnostic output.</p>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Alerts and explanation panels"
          classes={[".coreui-panel-note", ".coreui-panel-note--info", ".coreui-panel-note--warning", ".coreui-panel-note--success"]}
          source={`${sourceRoot}/styles/coreui-system.css`}
          description="Standardized explanation and feedback panels replacing one-off tinted boxes and border-left callouts."
        >
          <div className="coreui-showcase-panel-grid">
            <div className="coreui-panel-note coreui-panel-note--info">RAG searches your indexed documents before the model call.</div>
            <div className="coreui-panel-note coreui-panel-note--warning">Private mode disables traces and notifications for this build.</div>
            <div className="coreui-panel-note coreui-panel-note--success">Settings saved and applied to the active pipeline.</div>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Modal and overlay pattern"
          classes={[".coreui-modal-overlay", ".coreui-modal", ".coreui-modal-header", ".coreui-modal-close-btn"]}
          source={`${sourceRoot}/styles/coreui-system.css`}
          description="Shared modal surface, scrim, header, and close control used across settings and trace dialogs."
        >
          <div className="coreui-showcase-modal-preview">
            <div className="coreui-showcase-modal-scrim">
              <div className="coreui-showcase-modal-card">
                <div className="coreui-showcase-modal-card-header">
                  <strong>Dialog title</strong>
                  <button type="button" className="coreui-modal-close-btn" aria-label="Close modal preview">
                    <span className="material-symbols-outlined" aria-hidden="true">close</span>
                  </button>
                </div>
                <div className="coreui-showcase-modal-card-body">
                  <p className="coreui-text-muted-sm">Shared dialog shell for build configuration, trace detail, and settings overlays.</p>
                </div>
              </div>
            </div>
          </div>
        </ShowcaseItem>
      </ShowcaseSection>
      </>
      )}

      {subtab === "icons" && (
      <ShowcaseSection title="Icons">
        <ShowcaseItem
          name="Material Symbols"
          classes={[".material-symbols-outlined"]}
          source={`${sourceRoot}/components/SidebarNav.jsx and feature tabs`}
          description="Ligature icon font used for navigation, actions, status summaries, and compact visual labels."
        >
          <div className="coreui-showcase-icon-grid" aria-label="Icon preview">
            {["dashboard", "hub", "database", "science", "settings", "close"].map((icon) => (
              <span key={icon} className="coreui-showcase-icon-cell">
                <span className="material-symbols-outlined" aria-hidden="true">{icon}</span>
                <CodePill>{icon}</CodePill>
              </span>
            ))}
          </div>
        </ShowcaseItem>
      </ShowcaseSection>
      )}

      {subtab === "notifications" && (
      <>
      <ShowcaseSection title="Notification Cards">
        <ShowcaseItem
          name="Notification card variants"
          classes={[".notification-center-card", ".notification-center-card--error", ".notification-center-card--loading", ".notification-center-card--live"]}
          source={`${sourceRoot}/components/NotificationCenterShell.jsx, ${sourceRoot}/styles/components/NotificationCenter.css`}
          description="Floating notification cards for errors, loading states, events, and live activity. Rendered in a fixed bottom-right stack."
        >
          <div className="coreui-showcase-notification-stack">
            <Card className="notification-center-card notification-center-card--error coreui-showcase-notification-demo-card" elevation="var(--md-sys-elevation-level2)">
              <div className="notification-center-card-header">
                <span className="notification-center-card-header-title">Service unreachable</span>
                <button type="button" className="notification-center-card-close" aria-label="Dismiss">×</button>
              </div>
              <div className="notification-center-card-main">
                <div className="notification-center-card-message">Qdrant did not respond within the timeout window.</div>
              </div>
              <div className="notification-center-module-footer">
                <span className="notification-center-module-footer-source">RAG / Qdrant</span>
                <span className="notification-center-module-footer-time">14:22</span>
              </div>
            </Card>
            <Card className="notification-center-card notification-center-card--loading coreui-showcase-notification-demo-card" elevation="var(--md-sys-elevation-level2)">
              <div className="notification-center-card-header">
                <span className="notification-center-card-spinner" aria-hidden="true" />
                <span className="notification-center-card-header-title">Running RAG tests</span>
                <button type="button" className="notification-center-card-close" aria-label="Dismiss">×</button>
              </div>
              <div className="notification-center-card-main">
                <div className="notification-center-card-message">Test run in progress…</div>
                <div className="notification-center-card-timer">
                  <span className="material-symbols-outlined" aria-hidden="true">timer</span>
                  <span>Elapsed</span>
                  <strong>02:34</strong>
                </div>
              </div>
              <div className="notification-center-module-footer">
                <span className="notification-center-module-footer-source">RAG Tests</span>
                <span className="notification-center-module-footer-time">14:20</span>
              </div>
            </Card>
            <Card className="notification-center-card notification-center-card--live coreui-showcase-notification-demo-card" elevation="var(--md-sys-elevation-level2)">
              <div className="notification-center-card-header">
                <span className="notification-center-card-header-title">RAG Fusion Proxy</span>
                <button type="button" className="notification-center-card-close" aria-label="Close">×</button>
              </div>
              <div className="notification-center-card-live-slot">
                <div className="proxy-live-notification-row">
                  <span className="proxy-live-notification-label">Model</span>
                  <span className="proxy-live-notification-value">qwen2.5-coder:7b</span>
                </div>
              </div>
              <div className="notification-center-module-footer">
                <span className="notification-center-module-footer-source">RAG Fusion Proxy</span>
                <span className="notification-center-module-footer-time">14:25</span>
              </div>
            </Card>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Notification card anatomy"
          classes={[".notification-center-card-header", ".notification-center-card-main", ".notification-center-card-message", ".notification-center-card-timer", ".notification-center-card-actions", ".notification-center-module-footer"]}
          source={`${sourceRoot}/components/NotificationCenterShell.jsx, ${sourceRoot}/styles/components/NotificationCenter.css`}
          description="Each card has a header (title + spinner + close), a body (message, timer, action buttons), and a footer (source module + time)."
        >
          <Card className="notification-center-card coreui-showcase-notification-demo-card" elevation="var(--md-sys-elevation-level2)">
            <div className="notification-center-card-header">
              <span className="notification-center-card-spinner" aria-hidden="true" />
              <span className="notification-center-card-header-title">Installing extension</span>
              <button type="button" className="notification-center-card-close" aria-label="Dismiss">×</button>
            </div>
            <div className="notification-center-card-main">
              <div className="notification-center-card-message">Pulling Docker image and configuring runtime.</div>
              <div className="notification-center-card-timer">
                <span className="material-symbols-outlined" aria-hidden="true">timer</span>
                <span>Elapsed</span>
                <strong>01:12</strong>
              </div>
              <div className="notification-center-card-actions">
                <button type="button" className="notification-center-card-action-btn">View details</button>
              </div>
            </div>
            <div className="notification-center-module-footer">
              <span className="notification-center-module-footer-source">Extensions</span>
              <span className="notification-center-module-footer-time">14:18</span>
            </div>
          </Card>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="Action Buttons">
        <ShowcaseItem
          name="Action button (Bell and Clear)"
          classes={[".coreui-notification-action-btn", ".coreui-notification-action-btn-icon", ".coreui-notification-action-btn-label"]}
          source={`${sourceRoot}/components/CoreUINotificationActionButton.jsx, ${sourceRoot}/styles/components/CoreUINotificationActionButton.css`}
          description="Pill-shaped action buttons used in the floating notification center. The same component drives the Bell toggle, the Clear action, and any other overlay button, so heights and styling stay in lockstep."
        >
          <div className="coreui-showcase-notification-action-row">
            <CoreUINotificationActionButton icon="cleaning_services" label="Clear" />
            <CoreUINotificationActionButton icon="notifications" label="Notifications" />
          </div>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="History Popover">
        <ShowcaseItem
          name="Notification history dialog"
          classes={[".notification-center-popover", ".notification-center-popover-header", ".notification-center-popover-row"]}
          source={`${sourceRoot}/components/NotificationCenterShell.jsx, ${sourceRoot}/styles/components/NotificationCenter.css`}
          description="Glass-morphism popover with backdrop blur. Lists all persisted notifications sorted by time, with a Clear button in the header."
        >
          <div className="coreui-showcase-notification-popover-preview">
            <div className="notification-center-popover coreui-showcase-notification-popover-static">
              <div className="notification-center-popover-header">
                <span className="notification-center-popover-title">History</span>
                <CoreUIButton size="sm" variant="ghost">Clear</CoreUIButton>
              </div>
              <div className="notification-center-popover-list">
                <div className="notification-center-popover-row">
                  <div className="notification-center-popover-row-main">
                    <div className="notification-center-popover-row-title">Service unreachable</div>
                    <div className="notification-center-popover-row-msg">Qdrant did not respond within the timeout window.</div>
                  </div>
                  <div className="notification-center-module-footer">
                    <span className="notification-center-module-footer-source">RAG / Qdrant</span>
                    <span className="notification-center-module-footer-time">14:22</span>
                  </div>
                </div>
                <div className="notification-center-popover-row notification-center-popover-row--error">
                  <div className="notification-center-popover-row-main">
                    <div className="notification-center-popover-row-title">Security scan failed</div>
                    <div className="notification-center-popover-row-msg">Extension manifest validation error.</div>
                  </div>
                  <div className="notification-center-module-footer">
                    <span className="notification-center-module-footer-source">Extensions</span>
                    <span className="notification-center-module-footer-time">13:58</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="Module Labels">
        <ShowcaseItem
          name="Source module labels"
          classes={["notificationModuleLabels.js"]}
          source={`${sourceRoot}/components/notificationModuleLabels.js`}
          description="Maps internal source keys to human-readable display names shown in card footers and history rows."
        >
          <div className="coreui-showcase-notification-labels-grid">
            {[
              { key: "rag-tests", label: "RAG Tests" },
              { key: "rag-fusion-proxy", label: "RAG Fusion Proxy" },
              { key: "extensions", label: "Extensions" },
              { key: "rag", label: "RAG / Qdrant" },
              { key: "crawler", label: "Crawler / Indexer" },
              { key: "system", label: "System" },
            ].map(({ key, label }) => (
              <div key={key} className="coreui-showcase-notification-label-row">
                <CodePill>{key}</CodePill>
                <span className="material-symbols-outlined" aria-hidden="true">arrow_forward</span>
                <span>{label}</span>
              </div>
            ))}
          </div>
        </ShowcaseItem>
      </ShowcaseSection>
      </>
      )}
    </div>
  );
}

export default CoreUIShowcaseTab;
