import React from 'react';

const W = 48;
const H = 20;

/**
 * Mini sparkline: array of numbers -> SVG polyline.
 */
export default function Sparkline({ data, width = W, height = H, color = 'currentColor' }) {
  if (!Array.isArray(data) || data.length < 2) {
    return <span className="sparkline-empty" style={{ width, height, display: 'inline-block' }} />;
  }
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const pad = 1;
  const w = width - 2 * pad;
  const h = height - 2 * pad;
  const step = w / (data.length - 1);
  const points = data.map((v, i) => {
    const x = pad + i * step;
    const y = pad + h - ((v - min) / range) * h;
    return `${x},${y}`;
  }).join(' ');
  return (
    <svg className="sparkline" width={width} height={height} aria-hidden="true">
      <polyline
        fill="none"
        stroke={color}
        strokeWidth="1.2"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={points}
      />
    </svg>
  );
}
