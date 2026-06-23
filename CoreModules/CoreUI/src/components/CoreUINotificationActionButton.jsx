import Card from "./Card";
import "../styles/components/CoreUINotificationActionButton.css";

/**
 * Pill-shaped action button used by the floating notification center.
 * Renders a Material icon and an optional label inside a card-as-button surface.
 *
 * @param {Object} props
 * @param {string} [props.icon] - Material Symbol ligature name.
 * @param {string} [props.label] - Visible label rendered next to the icon.
 * @param {string} [props.ariaLabel] - Required for icon-only buttons; overrides the visible label.
 * @param {string} [props.title] - Tooltip text.
 * @param {boolean} [props.expanded] - Sets aria-expanded (for popover toggles).
 * @param {boolean} [props.hasPopup] - Sets aria-haspopup (for popover toggles).
 * @param {Function} [props.onClick] - Click handler.
 * @param {string} [props.className] - Additional CSS classes.
 */
export default function CoreUINotificationActionButton({
  icon,
  label,
  ariaLabel,
  title,
  expanded,
  hasPopup,
  onClick,
  className = "",
  type = "button",
  ...rest
}) {
  const accessibleLabel = ariaLabel || label || icon || "Notification action";
  const showLabel = Boolean(label);

  return (
    <Card
      as="button"
      type={type}
      interactive
      elevation="var(--md-sys-elevation-level3)"
      onClick={onClick}
      aria-label={accessibleLabel}
      title={title || accessibleLabel}
      aria-expanded={expanded}
      aria-haspopup={hasPopup}
      className={["coreui-notification-action-btn", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {icon ? (
        <span className="material-symbols-outlined coreui-notification-action-btn-icon" aria-hidden="true">
          {icon}
        </span>
      ) : null}
      {showLabel ? <span className="coreui-notification-action-btn-label">{label}</span> : null}
    </Card>
  );
}
