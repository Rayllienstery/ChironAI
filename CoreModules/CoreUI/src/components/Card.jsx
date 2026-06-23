
/**
 * Themed card surface with optional hover/interactive states.
 * Material 3 elevation tokens are used by default.
 *
 * @param {Object} props
 * @param {React.ElementType} [props.as='div'] - Element to render as.
 * @param {string} [props.className] - Additional CSS classes.
 * @param {boolean} [props.elevateOnHover=false] - Whether to elevate the card on hover.
 * @param {boolean} [props.interactive=false] - Whether the card is interactive (cursor pointer).
 * @param {string} [props.elevation] - CSS box-shadow value for the resting state.
 * @param {string} [props.elevationHover] - CSS box-shadow value for the hover state.
 * @param {string} [props.hoverBackground] - Background color on hover.
 * @param {string} [props.radius] - Border radius.
 * @param {string} [props.background] - Background color at rest.
 * @param {React.ReactNode} props.children - Card content.
 * @param {Object} [props.style] - Inline style overrides.
 * @param {Function} [props.onClick] - Click handler when interactive.
 */
export default function Card({
  as: Component = "div",
  className = "",
  elevateOnHover = false,
  interactive = false,
  elevation = "var(--md-sys-elevation-level1)",
  elevationHover = "var(--coreui-card-hover-shadow)",
  hoverBackground = "var(--md-sys-color-surface)",
  radius = "var(--md-sys-shape-corner-medium)",
  background = "var(--md-sys-color-surface)",
  children,
  style,
  ...rest
}) {
  const classes = ["app-card"];

  if (interactive) classes.push("app-card--interactive");
  if (elevateOnHover) classes.push("app-card--elevate-on-hover");

  if (className) classes.push(className);

  const mergedStyle = {
    "--app-card-bg": background,
    "--app-card-bg-hover": hoverBackground,
    "--app-card-radius": radius,
    "--app-card-box-shadow": elevation,
    "--app-card-box-shadow-hover": elevationHover,
    ...style,
  };

  return (
    <Component className={classes.join(" ")} style={mergedStyle} {...rest}>
      {children}
    </Component>
  );
}

