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
import ExtensionRuntimeModelCard from '../extensionRuntimeTab/ExtensionRuntimeModelCard';


export default function NotificationsShowcase() {
  return (
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
          name="Action button (Bell, Clear, and Latest)"
          classes={[".coreui-notification-action-btn", ".coreui-notification-action-btn-icon", ".coreui-notification-action-btn-label"]}
          source={`${sourceRoot}/components/CoreUINotificationActionButton.jsx, ${sourceRoot}/styles/components/CoreUINotificationActionButton.css`}
          description="Pill-shaped action buttons used in the floating notification center. Latest jumps back to the newest notifications when the stack is scrolled up."
        >
          <div className="coreui-showcase-notification-action-row">
            <CoreUINotificationActionButton icon="keyboard_arrow_down" label="Latest" />
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
  );
}
