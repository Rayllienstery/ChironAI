import { CodePill, ShowcaseItem, ShowcaseSection, TokenSwatch, FontCard, sourceRoot } from './CoreUIShowcasePrimitives';
import Card from '../Card';
import CoreUIButton from '../CoreUIButton';
import CoreUIBadge from '../CoreUIBadge';
import CoreUIDockerCard from '../CoreUIDockerCard';
import CoreUINotificationActionButton from '../CoreUINotificationActionButton';
import CoreUISubtabs from '../CoreUISubtabs';
import CoreUISlider from '../CoreUISlider';
import EmptyState from '../EmptyState';
import ExtensionRuntimeLoadingView, { buildExtensionRuntimeLoadingSteps } from '../ExtensionRuntimeLoadingView';
import StandByScreen from '../StandByScreen';
import CoreUIPipelinePreview from '../CoreUIPipelinePreview';
import CoreUIPillTabs from '../CoreUIPillTabs';
import ExtensionRuntimeModelCard from '../extensionRuntimeTab/ExtensionRuntimeModelCard';


export default function LayoutShowcase() {
  return (
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
              } as Record<string, unknown>) as never}
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
              } as Record<string, unknown>) as never}
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
              } as Record<string, unknown>) as never}
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
  );
}
