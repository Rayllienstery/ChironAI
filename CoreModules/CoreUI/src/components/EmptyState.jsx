import React from "react";
import "../styles/components/EmptyState.css";

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
