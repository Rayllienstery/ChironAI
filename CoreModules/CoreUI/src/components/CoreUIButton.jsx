import "../styles/components/CoreUIButtons.css";

function joinClasses(parts) {
  return parts.filter(Boolean).join(" ");
}

/**
 * A reusable button component supporting various styles and sizes.
 * 
 * @param {Object} props
 * @param {React.ElementType} [props.as='button'] - The component or HTML element to render as.
 * @param {'default'|'primary'|'danger'|'ghost'|'icon'} [props.variant='default'] - The visual style variant.
 * @param {'sm'|'md'|'icon'} [props.size='md'] - The size of the button.
 * @param {string} [props.className=''] - Additional CSS classes.
 * @param {string} [props.type] - The HTML button type (e.g., 'submit').
 * @param {React.ReactNode} props.children - The button content.
 */
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
