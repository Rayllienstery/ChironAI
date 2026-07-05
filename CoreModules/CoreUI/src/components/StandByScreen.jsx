import M3LoadingIndicator from "./M3LoadingIndicator";

/**
 * Renders a centered, branded standby/loading screen with a pulsing
 * animation and a label suitable for `aria-live` regions.
 *
 * @param {Object} props
 * @param {string} [props.brand="ChironAI"] - Brand text shown above the message.
 * @param {string} [props.message="Stand by..."] - Primary message.
 * @param {string} [props.submessage] - Optional secondary line under the message.
 * @param {string} [props.moduleName] - Module name used for the loading label and screen reader text.
 * @param {'sm'|'md'|'lg'} [props.size="md"] - Visual size variant of the card.
 */
export default function StandByScreen({
  brand = "ChironAI",
  message = "Stand by...",
  submessage,
  moduleName,
  size = "md",
}) {
  const sizeClass = `standby--${size}`;
  const loadingLabel = moduleName ? `Loading ${moduleName}` : "Loading";

  return (
    <div className={`standby-screen ${sizeClass}`} aria-live="polite">
      <div className="standby-card" role="status" aria-label={loadingLabel}>
        <M3LoadingIndicator
          size={size}
          className="standby-m3-loading-indicator"
          aria-hidden="true"
        />

        <div className="standby-copy">
          {brand && (
            <span className="standby-brand">{brand}</span>
          )}

          <span className="standby-message">{message}</span>
        </div>

        <div className="standby-module-meta">
          <span className="standby-module-label">Loading module</span>
          <span className="standby-module-name">{moduleName || "CoreUI"}</span>
        </div>

        {submessage && (
          <span className="standby-submessage">{submessage}</span>
        )}
      </div>
    </div>
  );
}
