import "../styles/components/CoreUIButtons.css";

function joinClasses(parts) {
  return parts.filter(Boolean).join(" ");
}

export default function CoreUIButton({
  as: Component = "button",
  variant = "default",
  size = "md",
  className = "",
  type,
  children,
  ...rest
}) {
  const classes = joinClasses([
    "coreui-btn",
    variant === "primary" && "coreui-btn-primary",
    variant === "danger" && "coreui-btn-danger",
    variant === "ghost" && "coreui-btn-ghost",
    variant === "icon" && "coreui-btn-icon",
    size === "sm" && "coreui-btn-small",
    size === "icon" && "coreui-btn-icon",
    className,
  ]);

  return (
    <Component
      className={classes}
      type={Component === "button" ? type || "button" : undefined}
      {...rest}
    >
      {children}
    </Component>
  );
}
