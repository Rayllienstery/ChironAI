import HelpViewer from './HelpViewer.jsx';

/**
 * Help tab shell for CoreUI sidebar navigation.
 */
export default function HelpTab({ initialSlug = null, onInitialSlugConsumed }) {
  return <HelpViewer initialSlug={initialSlug} onInitialSlugConsumed={onInitialSlugConsumed} />;
}
