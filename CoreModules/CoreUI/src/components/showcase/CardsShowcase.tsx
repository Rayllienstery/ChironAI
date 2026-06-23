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

const showcaseModelNoops = {
  onOpenMenu: () => {},
  onShowDetails: () => {},
  onModelMenuAction: () => {},
};

export default function CardsShowcase() {
  return (
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
          source={`${sourceRoot}/components/extensionRuntimeTab/ExtensionRuntimeModelCard.tsx, ${sourceRoot}/styles/components/ExtensionRuntimeTab.css`}
          description="Model card used in provider runtime tabs. It follows the CoreUI hoverable-card rule: neutral body, stronger accent-tinted hover shadow."
        >
          <div className="coreui-showcase-model-card-grid">
            <ExtensionRuntimeModelCard
              row={{ id: 'qwen2.5-coder:7b', provider_id: 'qwen', size: '5082316800', modified_at: '2026-04-28T00:00:00Z' }}
              index={0}
              extensionId="ollama"
              menuOpen={false}
              menuPosition={null}
              busyModelActionKey=""
              busyActionId=""
              templates={{}}
              {...showcaseModelNoops}
            />
            <ExtensionRuntimeModelCard
              row={{ id: 'llama3.2:3b', provider_id: 'meta', size: '2157969408', modified_at: '2026-04-25T00:00:00Z' }}
              index={1}
              extensionId="ollama"
              menuOpen={false}
              menuPosition={null}
              busyModelActionKey=""
              busyActionId=""
              templates={{}}
              {...showcaseModelNoops}
            />
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
  );
}
