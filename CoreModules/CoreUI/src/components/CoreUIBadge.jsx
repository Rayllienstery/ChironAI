function joinClasses(parts) {
  return parts.filter(Boolean).join(" ");
}

/**
 * A small inline label/badge with optional semantic tone.
 *
 * @param {Object} props
 * @param {React.ElementType} [props.as='span'] - Element to render the badge as.
 * @param {'neutral'|'success'|'warning'|'error'|'info'} [props.tone='neutral'] - Color tone.
 * @param {string} [props.className] - Additional CSS classes.
 * @param {React.ReactNode} props.children - Badge content.
 */
export default function CoreUIBadge({
  as: Component = "span",
  tone = "neutral",
  className = "",
  children,
  ...rest
}) {
  const classes = joinClasses([
    "coreui-badge",
    tone === "success" && "coreui-badge--success",
    tone === "warning" && "coreui-badge--warning",
    tone === "error" && "coreui-badge--error",
    tone === "info" && "coreui-badge--info",
    className,
  ]);

  return (
    <Component className={classes} {...rest}>
      {children}
    </Component>
  );
}
