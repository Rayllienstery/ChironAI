import { useCallback, useEffect, useMemo, useState } from "react";
import CoreUIBadge from "./CoreUIBadge";
import CoreUIPillTabs from "./CoreUIPillTabs";
import PerformanceAreaChart from "./PerformanceAreaChart";
import Sparkline from "./Sparkline";
import { getPerformanceSnapshot } from "../services/api";
import { t } from "../services/i18n";
import "../styles/components/PerformanceDetails.css";

const POLL_MS = 2000;
const MAX_SAMPLES = 1800;
const CHART_WINDOWS = [
  { id: "60s", samples: 30 },
  { id: "10m", samples: 300 },
  { id: "1h", samples: 1800 },
];
const ACCENT = {
  memory: "#0078D4",
  app: "#0F9D9A",
  gpu: "#8E6CFF",
};

function pushSample(history, value) {
  const next = [...history, Number.isFinite(value) ? value : 0];
  if (next.length > MAX_SAMPLES) next.shift();
  return next;
}

function sliceHistory(series, samples) {
  if (!Array.isArray(series) || series.length === 0) return [];
  return series.slice(-samples);
}

function kindLabel(kind) {
  if (kind === "container") return t("perf.details.kind_container");
  if (kind === "hermes") return t("perf.details.kind_hermes");
  return t("perf.details.kind_process");
}

function kindTone(kind) {
  if (kind === "container") return "info";
  if (kind === "hermes") return "success";
  return "neutral";
}

function formatGb(value, digits = 1) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return `${Number(value).toFixed(digits)} GB`;
}

function formatPct(value) {
  if (value == null || !Number.isFinite(Number(value))) return "—";
  return `${Number(value).toFixed(0)}%`;
}

function Stat({ label, value }) {
  return (
    <div className="perf-tm__stat">
      <span className="perf-tm__stat-label">{label}</span>
      <span className="perf-tm__stat-value">{value}</span>
    </div>
  );
}

function ChartBlock({ title, data, maxY, color, ariaLabel, windowLabel }) {
  return (
    <div className="perf-tm__chart-block">
      <div className="perf-tm__chart-label">{title}</div>
      <PerformanceAreaChart data={data} maxY={maxY} color={color} ariaLabel={ariaLabel} />
      <div className="perf-tm__chart-window">{windowLabel}</div>
    </div>
  );
}

function emptyHistory() {
  return {
    memUsed: [],
    appTotal: [],
    appHost: [],
    appDocker: [],
    gpuUtil: [],
    gpuMem: [],
    gpuTemp: [],
  };
}

export default function PerformanceDetailsSubtab() {
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [resource, setResource] = useState("app");
  const [chartWindow, setChartWindow] = useState("60s");
  const [history, setHistory] = useState(emptyHistory);

  const load = useCallback(async (signal) => {
    try {
      const data = await getPerformanceSnapshot();
      if (signal?.aborted) return;
      setSnapshot(data);
      setError(null);
      setLoading(false);
      setHistory((prev) => ({
        memUsed: pushSample(prev.memUsed, data?.memory?.used_gb),
        appTotal: pushSample(prev.appTotal, data?.app?.gb),
        appHost: pushSample(prev.appHost, data?.app?.host_gb),
        appDocker: pushSample(prev.appDocker, data?.app?.containers_gb),
        gpuUtil: pushSample(prev.gpuUtil, data?.gpu?.utilization_pct),
        gpuMem: pushSample(prev.gpuMem, (data?.gpu?.memory_used_mb || 0) / 1024),
        gpuTemp: pushSample(prev.gpuTemp, data?.gpu?.temperature_c),
      }));
    } catch (err) {
      if (signal?.aborted) return;
      setLoading(false);
      setError(err.message || t("perf.details.error"));
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    load(controller.signal);
    const timer = window.setInterval(() => load(controller.signal), POLL_MS);
    return () => {
      controller.abort();
      window.clearInterval(timer);
    };
  }, [load]);

  const memory = snapshot?.memory || {};
  const app = snapshot?.app || {};
  const gpu = snapshot?.gpu || null;
  const processes = Array.isArray(snapshot?.processes) ? snapshot.processes : [];
  const selected = gpu || resource !== "gpu" ? resource : "app";
  const windowOpt = CHART_WINDOWS.find((item) => item.id === chartWindow) || CHART_WINDOWS[0];
  const windowLabel = t(`perf.details.window_${windowOpt.id}`);
  const view = {
    memUsed: sliceHistory(history.memUsed, windowOpt.samples),
    appTotal: sliceHistory(history.appTotal, windowOpt.samples),
    appHost: sliceHistory(history.appHost, windowOpt.samples),
    appDocker: sliceHistory(history.appDocker, windowOpt.samples),
    gpuUtil: sliceHistory(history.gpuUtil, windowOpt.samples),
    gpuMem: sliceHistory(history.gpuMem, windowOpt.samples),
    gpuTemp: sliceHistory(history.gpuTemp, windowOpt.samples),
  };
  const windowTabs = CHART_WINDOWS.map((item) => ({
    id: item.id,
    label: t(`perf.details.window_${item.id}`),
  }));

  const railItems = useMemo(() => {
    const items = [
      {
        id: "memory",
        label: t("perf.details.memory"),
        value: memory.total_gb
          ? `${memory.used_gb ?? "—"}/${memory.total_gb} GB (${formatPct(memory.used_pct)})`
          : "—",
        spark: view.memUsed,
      },
      {
        id: "app",
        label: t("perf.details.chironai"),
        value: app.gb != null ? `${formatGb(app.gb)} · ${t("perf.details.host")} ${formatGb(app.host_gb)}` : "—",
        spark: view.appTotal,
      },
    ];
    if (gpu) {
      items.push({
        id: "gpu",
        label: gpu.name || t("perf.details.gpu"),
        value: `${formatPct(gpu.utilization_pct)} · ${gpu.temperature_c ?? "—"}°C`,
        spark: view.gpuUtil,
      });
    }
    return items;
  }, [memory, app, gpu, view]);

  return (
    <div className="perf-tm-wrap">
      <div className="perf-tm__toolbar">
        <CoreUIPillTabs
          tabs={windowTabs}
          value={chartWindow}
          onChange={setChartWindow}
          ariaLabel={t("perf.details.window")}
        />
      </div>
      <div className="perf-tm" data-resource={selected}>
      <div className="perf-tm__rail" role="tablist" aria-label={t("perf.details.resources")}>
        {railItems.map((item) => (
          <button
            key={item.id}
            type="button"
            role="tab"
            aria-selected={selected === item.id}
            className={`perf-tm__rail-item perf-tm__rail-item--${item.id}${selected === item.id ? " is-selected" : ""}`}
            onClick={() => setResource(item.id)}
          >
            <span className="perf-tm__spark" aria-hidden="true">
              <Sparkline data={item.spark} color={ACCENT[item.id]} width={72} height={28} />
            </span>
            <span className="perf-tm__rail-copy">
              <span className="perf-tm__rail-label">{item.label}</span>
              <span className="perf-tm__rail-value">{item.value}</span>
            </span>
          </button>
        ))}
      </div>

      <div className="perf-tm__main" role="tabpanel">
        {loading && !snapshot && (
          <div className="perf-tm__empty">
            <span className="material-symbols-outlined perf-startup__spinner" aria-hidden="true">autorenew</span>
            {t("common.loading")}
          </div>
        )}
        {error && !snapshot && (
          <div className="perf-tm__error">
            <span className="material-symbols-outlined" aria-hidden="true">error_outline</span>
            {error}
          </div>
        )}
        {!snapshot && !error && !loading && (
          <div className="perf-tm__empty">{t("perf.details.empty")}</div>
        )}

        {snapshot && selected === "memory" && (
          <>
            <header className="perf-tm__heading">
              <h3>{t("perf.details.memory")}</h3>
              <span>{formatGb(memory.total_gb, 1)}</span>
            </header>
            <ChartBlock
              title={`${t("perf.details.in_use")} ${memory.used_gb ?? "—"}/${memory.total_gb ?? "—"} GB`}
              data={view.memUsed}
              maxY={memory.total_gb || undefined}
              color={ACCENT.memory}
              ariaLabel={t("perf.details.memory")}
              windowLabel={windowLabel}
            />
            <div className="perf-tm__stats">
              <Stat label={t("perf.details.in_use")} value={`${formatGb(memory.used_gb)} (${formatPct(memory.used_pct)})`} />
              <Stat label={t("perf.details.available")} value={formatGb(memory.available_gb)} />
              <Stat
                label={t("perf.details.committed")}
                value={
                  memory.committed_total_gb
                    ? `${formatGb(memory.committed_gb)}/${formatGb(memory.committed_total_gb)}`
                    : formatGb(memory.committed_gb)
                }
              />
              {memory.cached_gb > 0 && (
                <Stat label={t("perf.details.cached")} value={formatGb(memory.cached_gb)} />
              )}
              <Stat
                label={t("perf.details.share")}
                value={`${formatGb(app.gb)} / ${formatGb(memory.total_gb)}`}
              />
            </div>
          </>
        )}

        {snapshot && selected === "app" && (
          <>
            <header className="perf-tm__heading">
              <h3>{t("perf.details.chironai")}</h3>
              <span>{formatGb(app.gb)}</span>
            </header>
            <div className="perf-tm__charts">
              <ChartBlock
                title={`${t("perf.details.host")} ${formatGb(app.host_gb)}`}
                data={view.appHost}
                color={ACCENT.app}
                ariaLabel={t("perf.details.host")}
                windowLabel={windowLabel}
              />
              <ChartBlock
                title={`${t("perf.details.docker")} ${formatGb(app.containers_gb)}`}
                data={view.appDocker}
                color={ACCENT.memory}
                ariaLabel={t("perf.details.docker")}
                windowLabel={windowLabel}
              />
            </div>
            <div className="perf-tm__stats">
              <Stat label={t("perf.details.chironai")} value={formatGb(app.gb)} />
              <Stat label={t("perf.details.host")} value={formatGb(app.host_gb)} />
              <Stat label={t("perf.details.docker")} value={formatGb(app.containers_gb)} />
              <Stat
                label={t("perf.details.share")}
                value={`${formatGb(app.gb)} / ${formatGb(memory.total_gb)} (${formatPct(
                  memory.total_bytes ? (100 * (app.bytes || 0)) / memory.total_bytes : 0
                )})`}
              />
            </div>
            <div className="perf-tm__table-wrap">
              <div className="perf-tm__table-title">{t("perf.details.processes")}</div>
              {processes.length === 0 ? (
                <div className="perf-tm__empty">{t("perf.details.empty")}</div>
              ) : (
                <table className="perf-tm__table">
                  <thead>
                    <tr>
                      <th>{t("perf.details.name")}</th>
                      <th>{t("perf.details.kind")}</th>
                      <th>{t("perf.details.pid")}</th>
                      <th>{t("perf.details.cpu")}</th>
                      <th>{t("perf.details.memory_col")}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {processes.map((row) => (
                      <tr key={row.id}>
                        <td>
                          <strong>{row.name}</strong>
                          {row.detail && row.detail !== row.name && (
                            <span>{row.detail}</span>
                          )}
                        </td>
                        <td>
                          <CoreUIBadge tone={kindTone(row.kind)}>{kindLabel(row.kind)}</CoreUIBadge>
                        </td>
                        <td>{row.pid ?? "—"}</td>
                        <td>{row.cpu_pct == null ? "—" : `${row.cpu_pct}%`}</td>
                        <td>{row.rss || "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </>
        )}

        {snapshot && selected === "gpu" && gpu && (
          <>
            <header className="perf-tm__heading">
              <h3>{t("perf.details.gpu")}</h3>
              <span>{gpu.name}</span>
            </header>
            <div className="perf-tm__charts perf-tm__charts--gpu">
              <ChartBlock
                title={`${t("perf.details.utilization")} ${formatPct(gpu.utilization_pct)}`}
                data={view.gpuUtil}
                maxY={100}
                color={ACCENT.gpu}
                ariaLabel={t("perf.details.utilization")}
                windowLabel={windowLabel}
              />
              <ChartBlock
                title={`${t("perf.details.gpu_memory")} ${((gpu.memory_used_mb || 0) / 1024).toFixed(1)}/${((gpu.memory_total_mb || 0) / 1024).toFixed(1)} GB`}
                data={view.gpuMem}
                maxY={(gpu.memory_total_mb || 0) / 1024 || undefined}
                color={ACCENT.gpu}
                ariaLabel={t("perf.details.gpu_memory")}
                windowLabel={windowLabel}
              />
              <ChartBlock
                title={`${t("perf.details.temperature")} ${gpu.temperature_c ?? "—"}°C`}
                data={view.gpuTemp}
                maxY={100}
                color={ACCENT.gpu}
                ariaLabel={t("perf.details.temperature")}
                windowLabel={windowLabel}
              />
            </div>
            <div className="perf-tm__stats">
              <Stat label={t("perf.details.utilization")} value={formatPct(gpu.utilization_pct)} />
              <Stat
                label={t("perf.details.gpu_memory")}
                value={
                  gpu.memory_used_mb != null && gpu.memory_total_mb != null
                    ? `${(gpu.memory_used_mb / 1024).toFixed(1)}/${(gpu.memory_total_mb / 1024).toFixed(1)} GB`
                    : "—"
                }
              />
              <Stat label={t("perf.details.temperature")} value={gpu.temperature_c != null ? `${gpu.temperature_c}°C` : "—"} />
              {gpu.driver_version && (
                <Stat label={t("perf.details.driver")} value={gpu.driver_version} />
              )}
            </div>
          </>
        )}
      </div>
      </div>
    </div>
  );
}
