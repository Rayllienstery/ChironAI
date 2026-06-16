import { useState } from 'react';
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


export default function ComponentsShowcase() {
  const [pipelineKey, setPipelineKey] = useState(0);

  return (
    <>
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
                type="button"
                className="rag-button primary"
                onClick={() => setPipelineKey((k) => k + 1)}
              >
                Replay Animation
              </button>
              <span style={{ fontSize: '12px', color: 'var(--md-sys-color-outline)' }}>
                Uses <code>animated</code> prop + <code>key</code> trigger
              </span>
            </div>
            <CoreUIPipelinePreview
                key={pipelineKey}
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
        </ShowcaseItem>
      </ShowcaseSection>
      
    </>
  );
}
