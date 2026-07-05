/**
 * Pre-React styles for the stand-by screen in index.html.
 * Loaded as a separate module entry so index.html does not need /src CSS links
 * (those break Vite's html-inline-proxy during production builds).
 */
import {
  M3Animator,
  drawIndicator,
  getMorphedShape,
  setupCanvas,
} from "@alerix/m3-loading-indicator";
import "./styles/tokens.css";
import "./styles/components/StandByScreen.css";

function readToken(name, fallback) {
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

function mountPrebootLoadingIndicator() {
  const canvas = document.getElementById("standby-m3-canvas");
  if (!canvas) {
    return null;
  }

  const size = 48;
  const ctx = setupCanvas(canvas, size);
  const animator = new M3Animator();
  const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  let frameId = 0;

  const render = (timestamp) => {
    animator.paused = motionQuery.matches;
    animator.update(timestamp);

    const shape = getMorphedShape(animator.morph);
    drawIndicator(ctx, size, shape, animator.rotation, {
      color: readToken("--md-sys-color-primary", "#6750a4"),
      containerColor: readToken("--md-sys-color-primary-container", "#eaddff"),
      contained: true,
    });

    frameId = requestAnimationFrame(render);
  };

  frameId = requestAnimationFrame(render);

  return () => cancelAnimationFrame(frameId);
}

mountPrebootLoadingIndicator();
