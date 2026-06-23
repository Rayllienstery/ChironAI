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


export default function ButtonsShowcase() {
  return (
    <>
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
      
    </>
  );
}
