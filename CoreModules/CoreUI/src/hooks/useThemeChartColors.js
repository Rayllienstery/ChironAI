import { useEffect, useState } from 'react';

/** Resolved M3 tokens for pie / chart fills (updates when accent or light/dark theme changes). */
const THEME_PIE_VAR_NAMES = [
  '--coreui-chart-1',
  '--coreui-chart-2',
  '--coreui-chart-3',
  '--coreui-chart-4',
  '--coreui-chart-5',
  '--coreui-chart-6',
  '--coreui-chart-7',
  '--coreui-chart-8',
  '--coreui-chart-9',
];

const FALLBACK_HEX = [
  '#5f6368',
  '#7a7a7a',
  '#8a8a8a',
  '#b0b0b0',
  '#9e9e9e',
  '#616161',
  '#757575',
  '#546e7a',
  '#90a4ae',
];

function readThemeColors() {
  if (typeof window === 'undefined') return [...FALLBACK_HEX];
  const s = getComputedStyle(document.documentElement);
  return THEME_PIE_VAR_NAMES.map((name, i) => {
    const v = s.getPropertyValue(name).trim();
    if (v && (v.startsWith('#') || v.startsWith('rgb') || v.startsWith('hsl'))) {
      return v;
    }
    return FALLBACK_HEX[i];
  });
}

/**
 * @returns {string[]} nine CSS color strings aligned with current theme accent
 */
export function useThemeChartColors() {
  const [colors, setColors] = useState(readThemeColors);

  useEffect(() => {
    const sync = () => setColors(readThemeColors());
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ['data-accent-color', 'class'],
    });
    return () => obs.disconnect();
  }, []);

  return colors;
}
