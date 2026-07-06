import '../styles/components/SupportUkraineBanner.css';

/**
 * Solidarity banner in the app header (left of the version label).
 */
export default function SupportUkraineBanner({ compact = false }) {
  return (
    <div
      className={`support-ukraine-banner${compact ? ' support-ukraine-banner--compact' : ''}`}
      role="note"
      aria-label="Support Ukraine"
    >
      <span className="support-ukraine-banner__flag" aria-hidden="true" title="Ukraine" />
      <span className="support-ukraine-banner__text">SUPPORT UKRAINE</span>
    </div>
  );
}
