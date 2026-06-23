import "../styles/components/EmptyState.css";

/**
 * Empty-state placeholder. Use to render a consistent message when a list/region is empty.
 *
 * @param {Object} props
 * @param {React.ElementType} [props.as='div'] - Element to render as.
 * @param {string} [props.className] - Additional CSS classes.
 * @param {React.ReactNode} props.children - Empty-state content.
 */
export default function EmptyState({
  as: Component = "div",
  className = "",
  children,
  ...rest
}) {
  return (
    <Component
      className={["coreui-empty-state", className].filter(Boolean).join(" ")}
      {...rest}
    >
      {children}
    </Component>
  );
}
