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


export default function ColorsShowcase() {
  return (
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
  );
}
