import React from "react";

export default function Card({
  as: Component = "div",
  className = "",
  elevateOnHover = false,
  interactive = false,
  elevation = "var(--md-sys-elevation-level1)",
  elevationHover = "var(--md-sys-elevation-level2)",
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

