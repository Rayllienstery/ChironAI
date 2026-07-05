import { useEffect, useState } from "react";
import { M3LoadingIndicator as M3Canvas } from "@alerix/m3-loading-indicator/react";

const SIZE_BY_VARIANT = { sm: 40, md: 48, lg: 64 };

function readToken(name, fallback) {
  if (typeof window === "undefined") {
    return fallback;
  }

  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/**
 * Material Design 3 expressive loading indicator wired to CoreUI theme tokens.
 *
 * @param {Object} props
 * @param {'sm'|'md'|'lg'|number} [props.size="md"] - Visual size preset or pixel size.
 * @param {boolean} [props.contained=true] - Draw the circular M3 container behind the shape.
 * @param {string} [props.className] - Optional class for the canvas element.
 */
export default function M3LoadingIndicator({
  size = "md",
  contained = true,
  className,
  ...rest
}) {
  const pixelSize = typeof size === "number" ? size : SIZE_BY_VARIANT[size] || 48;
  const [colors, setColors] = useState(() => ({
    color: readToken("--md-sys-color-primary", "#6750a4"),
    containerColor: readToken("--md-sys-color-primary-container", "#eaddff"),
  }));
  const [paused, setPaused] = useState(false);

  useEffect(() => {
    const syncColors = () => {
      setColors({
        color: readToken("--md-sys-color-primary", "#6750a4"),
        containerColor: readToken("--md-sys-color-primary-container", "#eaddff"),
      });
    };

    syncColors();

    const observer = new MutationObserver(syncColors);
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-accent-color", "class"],
    });

    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const syncMotion = () => setPaused(motionQuery.matches);
    syncMotion();
    motionQuery.addEventListener("change", syncMotion);

    return () => {
      observer.disconnect();
      motionQuery.removeEventListener("change", syncMotion);
    };
  }, []);

  return (
    <M3Canvas
      className={className}
      size={pixelSize}
      color={colors.color}
      containerColor={colors.containerColor}
      contained={contained}
      paused={paused}
      {...rest}
    />
  );
}
