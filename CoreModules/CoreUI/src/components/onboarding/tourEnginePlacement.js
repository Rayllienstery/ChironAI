const CARD_WIDTH = 384;
const CARD_HEIGHT_ESTIMATE = 240;
const VIEWPORT_MARGIN = 16;
const TARGET_GAP = 12;

/**
 * @param {string | undefined} selector
 * @returns {null | {
 *   top: number;
 *   left: number;
 *   width: number;
 *   height: number;
 *   borderRadius: string;
 *   placement: 'sidebar' | 'footer' | 'content';
 * }}
 */
export function measureTourTarget(selector) {
  if (!selector || typeof document === 'undefined') return null;
  const element = document.querySelector(selector);
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  const style = getComputedStyle(element);
  let placement = 'content';
  if (element.closest('.coreui-sidebar__footer')) {
    placement = 'footer';
  } else if (element.closest('.coreui-sidebar')) {
    placement = 'sidebar';
  }
  return {
    top: rect.top,
    left: rect.left,
    width: rect.width,
    height: rect.height,
    borderRadius: style.borderRadius || 'var(--md-sys-shape-corner-medium)',
    placement,
  };
}

/**
 * @param {ReturnType<typeof measureTourTarget>} spotlight
 */
export function computeTourCardStyle(spotlight) {
  if (!spotlight) {
    return {
      top: '50%',
      left: '50%',
      transform: 'translate(-50%, -50%)',
    };
  }

  const vw = window.innerWidth;
  const vh = window.innerHeight;
  const maxLeft = vw - CARD_WIDTH - VIEWPORT_MARGIN;

  if (spotlight.placement === 'sidebar') {
    const left = Math.min(
      Math.max(VIEWPORT_MARGIN, spotlight.left + spotlight.width + TARGET_GAP),
      maxLeft,
    );
    let top = spotlight.top + spotlight.height / 2;
    const half = CARD_HEIGHT_ESTIMATE / 2;
    top = Math.max(VIEWPORT_MARGIN + half, Math.min(vh - VIEWPORT_MARGIN - half, top));
    return { top, left, transform: 'translateY(-50%)' };
  }

  if (spotlight.placement === 'footer') {
    const left = Math.min(
      Math.max(VIEWPORT_MARGIN, spotlight.left + spotlight.width + TARGET_GAP),
      maxLeft,
    );
    const top = Math.max(
      VIEWPORT_MARGIN,
      spotlight.top - CARD_HEIGHT_ESTIMATE - TARGET_GAP,
    );
    return { top, left };
  }

  let top = spotlight.top + spotlight.height + TARGET_GAP;
  let left = Math.min(Math.max(VIEWPORT_MARGIN, spotlight.left), maxLeft);
  if (top + CARD_HEIGHT_ESTIMATE > vh - VIEWPORT_MARGIN) {
    top = Math.max(VIEWPORT_MARGIN, spotlight.top - CARD_HEIGHT_ESTIMATE - TARGET_GAP);
  }
  return { top, left };
}
