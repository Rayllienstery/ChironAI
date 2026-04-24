function joinClasses(parts) {
  return parts.filter(Boolean).join(" ");
}

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
