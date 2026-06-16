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


export default function DataShowcase() {
  return (
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
  );
}
