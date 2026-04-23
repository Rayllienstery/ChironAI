import Card from "./Card";
import CoreUIButton from "./CoreUIButton";
import CoreUIPillTabs from "./CoreUIPillTabs";
import CoreUISlider from "./CoreUISlider";
import EmptyState from "./EmptyState";
import "../styles/components/CoreUIShowcaseTab.css";

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

function CoreUIShowcaseTab() {
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

      <ShowcaseSection title="Foundations">
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

      <ShowcaseSection title="Core Components">
        <ShowcaseItem
          name="Card"
          classes={[".app-card", ".app-card--interactive", ".app-card--elevate-on-hover"]}
          source={`${sourceRoot}/components/Card.jsx`}
          description="Compact elevated surface with optional interaction and hover elevation."
        >
          <Card interactive elevateOnHover className="coreui-showcase-demo-card">
            Interactive card surface
          </Card>
        </ShowcaseItem>

        <ShowcaseItem
          name="CoreUIButton"
          classes={[".coreui-btn", ".coreui-btn-primary", ".coreui-btn-ghost", ".coreui-btn-small"]}
          source={`${sourceRoot}/components/CoreUIButton.jsx`}
          description="Shared button primitive for toolbar and panel actions."
        >
          <div className="coreui-showcase-button-row">
            <CoreUIButton variant="primary">Primary</CoreUIButton>
            <CoreUIButton>Default</CoreUIButton>
            <CoreUIButton variant="ghost">Ghost</CoreUIButton>
            <CoreUIButton size="sm">Small</CoreUIButton>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Action button groups"
          classes={["CoreUIButton", ".dashboard-primary-btn", ".dashboard-secondary-btn"]}
          source={`${sourceRoot}/components/CoreUIButton.jsx, ${sourceRoot}/styles/components/DashboardTab.css`}
          description="Standard replacement for the older capsule action buttons used by Open WebUI, Dashboard, Ollama, and proxy screens."
        >
          <div className="coreui-showcase-action-button-stack">
            <div className="coreui-showcase-button-row">
              <CoreUIButton>Refresh</CoreUIButton>
              <CoreUIButton variant="primary">Stop service</CoreUIButton>
            </div>
            <div className="coreui-showcase-button-row">
              <CoreUIButton>Use LLM Proxy default</CoreUIButton>
              <CoreUIButton>Clear saved (env/default)</CoreUIButton>
              <CoreUIButton variant="primary">Save backend</CoreUIButton>
            </div>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="CoreUIPillTabs"
          classes={[".coreui-pill-tablist", ".coreui-pill-tab", ".coreui-pill-tab-active"]}
          source={`${sourceRoot}/components/CoreUIPillTabs.jsx`}
          description="Reusable horizontal segmented navigation for sub-tabs and mode switching."
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
          name="EmptyState"
          classes={[".coreui-empty-state"]}
          source={`${sourceRoot}/components/EmptyState.jsx`}
          description="Dashed neutral panel for missing data, unavailable integrations, and empty results."
        >
          <EmptyState>No records available for this filter.</EmptyState>
        </ShowcaseItem>
      </ShowcaseSection>

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
              <span className="status-label">Ollama</span>
              <span className="status-text">stopped</span>
            </span>
            <span className="status-text-updating">
              <span className="status-spinner" />
              checking
            </span>
          </div>
        </ShowcaseItem>
      </ShowcaseSection>

      <ShowcaseSection title="Forms & Controls">
        <ShowcaseItem
          name="Text fields"
          classes={[".coreui-showcase-field", "input", "textarea"]}
          source={`${sourceRoot}/styles/components/CoreUIShowcaseTab.css`}
          description="Theme-aware text inputs for form previews and future shared control extraction."
        >
          <div className="coreui-showcase-form-grid">
            <label className="coreui-showcase-field">
              <span>Model name</span>
              <input value="qwen2.5-coder" readOnly />
            </label>
            <label className="coreui-showcase-field">
              <span>Prompt note</span>
              <textarea value="Reusable form surface." readOnly />
            </label>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Select and boolean controls"
          classes={["select:not([multiple]):not([size])", ".coreui-showcase-check", ".coreui-showcase-switch"]}
          source={`${sourceRoot}/styles/layout.css, ${sourceRoot}/styles/components/CoreUIShowcaseTab.css`}
          description="Native select inherits the global chevron; checkbox and switch previews use showcase-local styling."
        >
          <div className="coreui-showcase-control-row">
            <label className="coreui-showcase-field coreui-showcase-select-field">
              <span>Mode</span>
              <select value="system" onChange={() => {}} aria-label="Mode preview">
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </select>
            </label>
            <label className="coreui-showcase-check">
              <input type="checkbox" checked readOnly />
              <span>Enabled</span>
            </label>
            <label className="coreui-showcase-switch">
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
              <span role="cell"><span className="coreui-showcase-badge">cached</span></span>
            </div>
            <div className="coreui-showcase-data-row" role="row">
              <span role="cell">proxy.trace</span>
              <span role="cell">2.4 s</span>
              <span role="cell"><span className="coreui-showcase-badge coreui-showcase-badge-warning">slow</span></span>
            </div>
          </div>
        </ShowcaseItem>

        <ShowcaseItem
          name="Feedback badges"
          classes={[".coreui-showcase-badge", ".coreui-showcase-feedback"]}
          source={`${sourceRoot}/styles/components/CoreUIShowcaseTab.css`}
          description="Neutral, success, warning, and error feedback tokens for inline state display."
        >
          <div className="coreui-showcase-feedback-row">
            <span className="coreui-showcase-badge">neutral</span>
            <span className="coreui-showcase-badge coreui-showcase-badge-success">success</span>
            <span className="coreui-showcase-badge coreui-showcase-badge-warning">warning</span>
            <span className="coreui-showcase-badge coreui-showcase-badge-error">error</span>
          </div>
        </ShowcaseItem>
      </ShowcaseSection>

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
    </div>
  );
}

export default CoreUIShowcaseTab;
