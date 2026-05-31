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
        <div className="standby-loading-indicator" aria-hidden="true">
          <span className="standby-loading-shape standby-loading-shape--one" />
          <span className="standby-loading-shape standby-loading-shape--two" />
          <span className="standby-loading-shape standby-loading-shape--three" />
        </div>

        <div className="standby-copy">
          {brand && (
            <span className="standby-brand">{brand}</span>
          )}

          <span className="standby-message">{message}</span>
        </div>

        <div className="standby-progress-stack">
          <div
            className="standby-progress"
            role="progressbar"
            aria-label={loadingLabel}
            aria-valuetext={moduleName ? loadingLabel : submessage || message}
          >
            <span className="standby-progress-fill standby-progress-fill--lead" />
            <span className="standby-progress-fill standby-progress-fill--trail" />
          </div>

          <div className="standby-progress-meta">
            <span className="standby-module-label">Loading module</span>
            <span className="standby-module-name">{moduleName || "CoreUI"}</span>
          </div>
        </div>

        {submessage && (
          <span className="standby-submessage">{submessage}</span>
        )}
      </div>
    </div>
  );
}
