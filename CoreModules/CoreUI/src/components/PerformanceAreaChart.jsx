/**
 * Task Manager-style area chart: filled series against a fixed or auto max.
 */
export default function PerformanceAreaChart({
  data,
  maxY,
  color = "var(--md-sys-color-primary)",
  height = 168,
  ariaLabel,
  className = "",
}) {
  const values = Array.isArray(data)
    ? data.map((value) => Number(value)).filter((value) => Number.isFinite(value))
    : [];
  const series = values.length >= 2 ? values : values.length === 1 ? [values[0], values[0]] : [0, 0];
  const width = 640;
  const padY = 6;
  const peak = Math.max(...series, 0);
  const yMax = maxY && maxY > 0 ? maxY : Math.max(peak * 1.08, 0.1);
  const coords = series.map((value, index) => {
    const x = (index / (series.length - 1)) * width;
    const ratio = Math.min(1, Math.max(0, value / yMax));
    const y = padY + (1 - ratio) * (height - 2 * padY);
    return [x, y];
  });
  const line = coords.map(([x, y]) => `${x.toFixed(2)},${y.toFixed(2)}`).join(" ");
  const area = `0,${height} ${line} ${width},${height}`;
  const ticks = [0.25, 0.5, 0.75];

  return (
    <svg
      className={`perf-tm-chart ${className}`.trim()}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      role="img"
      aria-label={ariaLabel}
    >
      <rect className="perf-tm-chart__bg" x="0" y="0" width={width} height={height} />
      {ticks.map((tick) => {
        const y = padY + (1 - tick) * (height - 2 * padY);
        return (
          <line
            key={tick}
            className="perf-tm-chart__grid"
            x1="0"
            x2={width}
            y1={y}
            y2={y}
          />
        );
      })}
      <polygon className="perf-tm-chart__area" points={area} fill={color} />
      <polyline
        className="perf-tm-chart__line"
        points={line}
        stroke={color}
        fill="none"
      />
    </svg>
  );
}
