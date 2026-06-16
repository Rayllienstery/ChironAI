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


export default function IconsShowcase() {
  return (
    <>
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
      
    </>
  );
}
