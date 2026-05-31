import { useEffect, useState } from "react";

const ICON_MAP = {
  progress_activity: "progress_activity",
  sync: "sync",
  hourglass: "hourglass",
  settings: "settings",
  tab: "tab",
  cloud_sync: "cloud_sync",
  database: "database",
  network_intelligence: "network_intelligence",
  neurology: "neurology",
  cognition: "cognition",
  psychology: "psychology",
  auto_awesome: "auto_awesome",
};

export default function StandByScreen({
  message = "Stand by",
  submessage,
  icon = "progress_activity",
  size = "md",
}) {
  const [phase, setPhase] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setPhase((p) => (p + 1) % 3), 1200);
    return () => clearInterval(t);
  }, []);

  const sizeClass = `standby--${size}`;
  const iconName = ICON_MAP[icon] || "progress_activity";

  return (
    <div className={`standby-screen ${sizeClass}`}>
      <div className="standby-card">
        <div className="standby-icon-ring">
          <span className="standby-icon material-symbols-outlined">
            {iconName}
          </span>
        </div>

        <div className="standby-dots">
          <span
            className="standby-dot"
            data-active={phase === 0 || undefined}
          />
          <span
            className="standby-dot"
            data-active={phase === 1 || undefined}
          />
          <span
            className="standby-dot"
            data-active={phase === 2 || undefined}
          />
        </div>

        <span className="standby-message">{message}</span>

        {submessage && (
          <span className="standby-submessage">{submessage}</span>
        )}
      </div>
    </div>
  );
}
