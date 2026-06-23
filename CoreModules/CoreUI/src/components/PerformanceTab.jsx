import { useState, useEffect, useCallback } from "react";
import CoreUIPillTabs from "./CoreUIPillTabs";
import CoreUISubtabs from "./CoreUISubtabs";
import CoreUIModal from "./CoreUIModal";
import Card from "./Card";
import { getStartupPerformance } from "../services/api";
import { getModuleTimings, subscribeModuleTimings } from "../services/moduleTimings";
import "../styles/components/PerformanceTab.css";

const SUBTABS = [{ id: "startup", label: "Startup" }];

const MODAL_TABS = [
  { id: "summary", label: "Summary" },
  { id: "debug", label: "Debug Log" },
];

const STATUS_ICON = {
  ok: "check_circle",
  failed: "error",
  in_progress: "pending",
  skipped: "remove_circle",
};

const STATUS_TONE = {
  ok: "success",
  failed: "neutral",
  in_progress: "primary",
  skipped: "neutral",
};

function formatMs(ms) {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${(ms / 1000).toFixed(2)} s`;
}

function formatEpoch(epochMs) {
  if (!epochMs) return null;
  try {
    return new Date(epochMs).toLocaleTimeString();
  } catch {
    return null;
  }
}

function formatSources(sources) {
  if (!Array.isArray(sources) || sources.length === 0) return "navigation";
  return sources.join(", ");
}

function useModuleTimingSnapshot() {
  const [modules, setModules] = useState(() => getModuleTimings());

  useEffect(() => {
    const refresh = () => setModules(getModuleTimings());
    const unsubscribe = subscribeModuleTimings(refresh);
    const intervalId = window.setInterval(refresh, 500);
    refresh();
    return () => {
      unsubscribe();
      window.clearInterval(intervalId);
    };
  }, []);

  return modules;
}

// ---------------------------------------------------------------------------
// Waterfall bar for the Summary subtab
// ---------------------------------------------------------------------------

function WaterfallBar({ durationMs, totalMs, status }) {
  const pct = totalMs > 0 ? Math.min(100, (durationMs / totalMs) * 100) : 0;
  return (
    <div className="perf-waterfall-track" aria-hidden="true">
      <div
        className={`perf-waterfall-fill perf-waterfall-fill--${status || "ok"}`}
        style={{ width: `${pct}%` }}
      />
    </div>
  );
}

function ModuleLoadMonitor({ modules }) {
  const active = modules.filter((mod) => mod.status === "in_progress");
  const recent = [...modules]
    .filter((mod) => mod.status !== "in_progress")
    .sort((a, b) => (b.loaded_at || 0) - (a.loaded_at || 0))
    .slice(0, 8);
  const visible = active.length > 0 ? active : recent;

  return (
    <Card className="perf-startup__inner-card perf-module-monitor" elevation="var(--md-sys-elevation-level1)">
      <div className="perf-module-monitor__header">
        <div>
          <h3 className="perf-startup__title">Lazy Module Loads</h3>
          <p className="perf-startup__subtitle">
            Live dynamic-import status for tabs and nested panels.
          </p>
        </div>
        <div className="perf-module-monitor__count">
          <span>{active.length}</span>
          loading now
        </div>
      </div>

      {visible.length === 0 && (
        <div className="perf-module-monitor__empty">
          No lazy module loads recorded in this browser session yet.
        </div>
      )}

      {visible.length > 0 && (
        <div className="perf-module-monitor__table" role="table" aria-label="Lazy module load status">
          <div className="perf-module-monitor__row perf-module-monitor__row--head" role="row">
            <span role="columnheader">Module</span>
            <span role="columnheader">Status</span>
            <span role="columnheader">Step</span>
            <span role="columnheader">Source</span>
            <span role="columnheader">Elapsed</span>
          </div>
          {visible.map((mod) => (
            <div key={mod.id} className="perf-module-monitor__row" role="row">
              <span role="cell" className="perf-module-monitor__module">{mod.label}</span>
              <span role="cell" className={`perf-module-monitor__status perf-module-monitor__status--${mod.status}`}>
                <span className="material-symbols-outlined" aria-hidden="true">
                  {STATUS_ICON[mod.status] || "fiber_manual_record"}
                </span>
                {mod.status === "in_progress" ? "loading" : mod.status}
              </span>
              <span role="cell">{mod.step || "import()"}</span>
              <span role="cell">{formatSources(mod.sources)}</span>
              <span role="cell" className="perf-module-monitor__elapsed">
                {formatMs(mod.elapsed_ms ?? mod.duration_ms)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Summary subtab inside the modal
// ---------------------------------------------------------------------------

function PhaseSummary({ phase, report }) {
  const totalMs = report?.total_duration_ms || phase.duration_ms || 1;

  return (
    <div className="perf-summary">
      <div className="perf-summary__header">
        <span
          className={`material-symbols-outlined perf-summary__status-icon perf-summary__status-icon--${phase.status}`}
          aria-hidden="true"
        >
          {STATUS_ICON[phase.status] || "info"}
        </span>
        <div>
          <div className="perf-summary__title">{phase.label}</div>
          <div className="perf-summary__desc">{phase.description}</div>
        </div>
        <div className="perf-summary__duration">{formatMs(phase.duration_ms)}</div>
      </div>

      <div className="perf-summary__waterfall-row">
        <WaterfallBar
          durationMs={phase.duration_ms}
          totalMs={totalMs}
          status={phase.status}
        />
      </div>

      {Array.isArray(phase.steps) && phase.steps.length > 0 && (
        <div className="perf-summary__steps">
          <div className="perf-summary__steps-title">Sub-steps</div>
          {phase.steps.map((step) => (
            <div key={step.id} className="perf-summary__step">
              <span
                className={`material-symbols-outlined perf-summary__step-icon perf-summary__step-icon--${step.status}`}
                aria-hidden="true"
              >
                {STATUS_ICON[step.status] || "fiber_manual_record"}
              </span>
              <div className="perf-summary__step-info">
                <div className="perf-summary__step-label">{step.label}</div>
                {step.description && (
                  <div className="perf-summary__step-desc">{step.description}</div>
                )}
                <WaterfallBar
                  durationMs={step.duration_ms}
                  totalMs={phase.duration_ms || 1}
                  status={step.status}
                />
              </div>
              <div className="perf-summary__step-ms">
                {formatMs(step.duration_ms)}
                {step.extra_ms != null && (
                  <span className="perf-summary__step-delta" title="Time spent in this step only">
                    +{formatMs(step.extra_ms)}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {Array.isArray(phase.module_loads) && phase.module_loads.length > 0 && (
        <div className="perf-summary__modules">
          <div className="perf-summary__steps-title">
            Lazy Module Loads
            <span className="perf-summary__modules-count">
              {phase.module_loads.length} chunk{phase.module_loads.length !== 1 ? "s" : ""}
            </span>
          </div>
          <div className="perf-summary__modules-hint">
            Recorded as each React.lazy() chunk was first imported during this session.
          </div>
          {phase.module_loads.map((mod) => {
            const maxMs = Math.max(...phase.module_loads.map((m) => m.duration_ms), 1);
            return (
              <div key={mod.id} className="perf-summary__mod-row">
                <span
                  className={`material-symbols-outlined perf-summary__step-icon perf-summary__step-icon--${mod.status}`}
                  aria-hidden="true"
                >
                  {STATUS_ICON[mod.status] || "fiber_manual_record"}
                </span>
                <div className="perf-summary__step-info">
                  <div className="perf-summary__step-label">{mod.label}</div>
                  <WaterfallBar
                    durationMs={mod.duration_ms}
                    totalMs={maxMs}
                    status={mod.status}
                  />
                </div>
                <div className="perf-summary__step-ms">{formatMs(mod.duration_ms)}</div>
              </div>
            );
          })}
        </div>
      )}

      {phase.metadata && Object.keys(phase.metadata).length > 0 && (
        <div className="perf-summary__meta">
          <div className="perf-summary__steps-title">Metadata</div>
          <dl className="perf-summary__meta-list">
            {Object.entries(phase.metadata).map(([k, v]) => (
              <div key={k} className="perf-summary__meta-row">
                <dt className="perf-summary__meta-key">{k}</dt>
                <dd className="perf-summary__meta-val">
                  {Array.isArray(v) ? v.join(", ") || "—" : String(v ?? "—")}
                </dd>
              </div>
            ))}
          </dl>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Debug Log subtab inside the modal
// ---------------------------------------------------------------------------

function PhaseDebugLog({ phase }) {
  const json = JSON.stringify(phase, null, 2);

  const handleExport = () => {
    try {
      const blob = new Blob([json], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `startup-phase-${phase.id ?? "unknown"}.json`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // Fallback: copy to clipboard
      navigator.clipboard?.writeText(json).catch(() => {});
    }
  };

  return (
    <div className="perf-debug">
      <div className="perf-debug__toolbar">
        <div className="perf-debug__hint">
          Full phase record — all timing, sub-steps, log lines, and metadata.
        </div>
        <button
          type="button"
          className="perf-debug__export-btn"
          onClick={handleExport}
          aria-label="Export debug log as JSON file"
        >
          <span className="material-symbols-outlined" aria-hidden="true">
            download
          </span>
          Export JSON
        </button>
      </div>
      {Array.isArray(phase.log_lines) && phase.log_lines.length > 0 && (
        <div className="perf-debug__section">
          <div className="perf-debug__section-title">Log lines</div>
          <pre className="perf-debug__pre perf-debug__pre--logs">
            {phase.log_lines.join("\n")}
          </pre>
        </div>
      )}
      <div className="perf-debug__section">
        <div className="perf-debug__section-title">Raw JSON</div>
        <pre className="perf-debug__pre">{json}</pre>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Phase detail modal
// ---------------------------------------------------------------------------

function PhaseModal({ phase, report, onClose }) {
  const [modalTab, setModalTab] = useState("summary");

  return (
    <CoreUIModal
      title={phase.label}
      onClose={onClose}
      className="perf-phase-modal"
    >
      <CoreUISubtabs
        tabs={MODAL_TABS}
        value={modalTab}
        onChange={setModalTab}
        ariaLabel="Phase detail sections"
        className="perf-modal-subtabs"
      />
      {modalTab === "summary" && (
        <PhaseSummary phase={phase} report={report} />
      )}
      {modalTab === "debug" && <PhaseDebugLog phase={phase} />}
    </CoreUIModal>
  );
}

// ---------------------------------------------------------------------------
// Phase section row (replaces pipeline step)
// ---------------------------------------------------------------------------

function PhaseRow({ phase, onSelect, isLast }) {
  const icon = STATUS_ICON[phase.status] || "radio_button_unchecked";
  const tone = STATUS_TONE[phase.status] || "neutral";

  return (
    <>
      <button
        type="button"
        className={`perf-phase-row perf-phase-row--${tone}`}
        onClick={() => onSelect(phase)}
        aria-label={`${phase.label}. Click for details.`}
      >
        <span
          className={`material-symbols-outlined perf-phase-row__icon perf-phase-row__icon--${phase.status}`}
          aria-hidden="true"
        >
          {icon}
        </span>
        <div className="perf-phase-row__body">
          <span className="perf-phase-row__label">{phase.label}</span>
          {phase.description && (
            <span className="perf-phase-row__desc">{phase.description}</span>
          )}
        </div>
        <span className="perf-phase-row__duration">{formatMs(phase.duration_ms)}</span>
      </button>
      {!isLast && <div className="perf-phase-row__sep" aria-hidden="true" />}
    </>
  );
}

// ---------------------------------------------------------------------------
// Startup subtab — section list inside one card
// ---------------------------------------------------------------------------
// Build browser timing sub-steps from Navigation Timing fields.
// All duration_ms values are cumulative offsets from navigationStart so the
// numbers read as "milestone reached at T ms" — consistent with the server
// phases where start_offset_ms plays the same role.
function buildBrowserSteps(b) {
  const nav = b.navigationStart;
  const steps = [];

  const push = (id, label, description, ts) => {
    if (ts && ts > nav) {
      steps.push({ id, label, description, duration_ms: ts - nav, status: "ok" });
    }
  };

  push("ttfb",              "TTFB",             "Time to first byte from the server",           b.responseStart);
  push("response_end",      "Document received","Full HTML document downloaded",                 b.responseEnd);
  push("dom_interactive",   "DOM Interactive",  "HTML parsed — DOM ready, deferred scripts pending", b.domInteractive);
  push("dom_content_loaded","DOMContentLoaded", "Deferred scripts executed",                     b.domContentLoadedEventEnd);
  push("load_event",        "Load Event",       "All sub-resources (stylesheets, images) loaded", b.loadEventEnd);

  // React Bootstrap = gap between last load event and actual React mount
  if (b.reactMountMs != null) {
    const loadEndOffset = b.loadEventEnd ? b.loadEventEnd - nav : 0;
    const bootstrapMs = b.reactMountMs - loadEndOffset;
    steps.push({
      id: "react_bootstrap",
      label: "React Bootstrap",
      description: "JS bundle parse + React component tree initialized",
      duration_ms: b.reactMountMs,
      extra_ms: bootstrapMs > 0 ? bootstrapMs : 0,
      status: "ok",
    });
  }

  return steps;
}

// ---------------------------------------------------------------------------

function StartupSubtab() {
  const [report, setReport] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedPhase, setSelectedPhase] = useState(null);
  const moduleTimings = useModuleTimingSnapshot();

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getStartupPerformance();
      setReport(data);
    } catch (err) {
      setError(err.message || "Failed to load startup performance data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const phases = report?.phases || [];
  const totalMs = report?.total_duration_ms ?? 0;
  const startTime = formatEpoch(report?.server_start_epoch_ms);

  // Build unified phase list (server phases + browser phase)
  const allPhases = [...phases];
  const browser = report?.browser_timing;
  if (browser && browser.navigationStart && browser.reactMountMs != null) {
    allPhases.push({
      id: "webui_load",
      label: "WebUI (Browser)",
      description: "Page load → React mount",
      duration_ms: browser.reactMountMs,
      start_offset_ms: 0,
      status: "ok",
      steps: buildBrowserSteps(browser),
      module_loads: moduleTimings,
      log_lines: [],
      metadata: browser,
    });
  }

  return (
    <Card className="perf-startup__outer" elevation="var(--md-sys-elevation-level1)">

      {/* Inner card 1: stats + refresh */}
      <Card className="perf-startup__inner-card" elevation="var(--md-sys-elevation-level1)">
        <div className="perf-startup__topbar">
          <div className="perf-startup__banner">
            {loading && (
              <>
                <div className="perf-startup__banner-stat">
                  <span className="perf-startup__banner-label">Total startup</span>
                  <span className="perf-startup__banner-value perf-startup__skeleton" aria-hidden="true">—</span>
                </div>
                <div className="perf-startup__banner-stat">
                  <span className="perf-startup__banner-label">Started at</span>
                  <span className="perf-startup__banner-value perf-startup__skeleton" aria-hidden="true">—</span>
                </div>
                <div className="perf-startup__banner-stat">
                  <span className="perf-startup__banner-label">Phases</span>
                  <span className="perf-startup__banner-value perf-startup__skeleton" aria-hidden="true">—</span>
                </div>
              </>
            )}
            {!loading && !error && report && (
              <>
                <div className="perf-startup__banner-stat">
                  <span className="perf-startup__banner-label">Total startup</span>
                  <span className="perf-startup__banner-value">{formatMs(totalMs)}</span>
                </div>
                {startTime && (
                  <div className="perf-startup__banner-stat">
                    <span className="perf-startup__banner-label">Started at</span>
                    <span className="perf-startup__banner-value">{startTime}</span>
                  </div>
                )}
                <div className="perf-startup__banner-stat">
                  <span className="perf-startup__banner-label">Phases</span>
                  <span className="perf-startup__banner-value">{allPhases.length}</span>
                </div>
              </>
            )}
          </div>
          <button
            type="button"
            className="perf-startup__refresh"
            onClick={load}
            aria-label="Refresh startup timing data"
          >
            <span className="material-symbols-outlined" aria-hidden="true">refresh</span>
            Refresh
          </button>
        </div>
      </Card>

      <ModuleLoadMonitor modules={moduleTimings} />

      {/* Inner card 2: title + phase rows */}
      <Card className="perf-startup__inner-card perf-startup__inner-card--phases" elevation="var(--md-sys-elevation-level1)">
        <div className="perf-startup__section-header">
          <h3 className="perf-startup__title">Application Startup</h3>
          <p className="perf-startup__subtitle">
            Every module loaded when the server starts. Click any phase for a
            detailed timing breakdown.
          </p>
        </div>

        {loading && (
          <div className="perf-startup__loading">
            <span className="material-symbols-outlined perf-startup__spinner" aria-hidden="true">
              autorenew
            </span>
            Loading startup timing…
          </div>
        )}
        {error && (
          <div className="perf-startup__error">
            <span className="material-symbols-outlined" aria-hidden="true">error_outline</span>
            {error}
          </div>
        )}
        {!loading && !error && allPhases.length === 0 && (
          <div className="perf-startup__empty">
            No startup timing data yet. Restart the server to collect data.
          </div>
        )}

        {!loading && !error && allPhases.length > 0 && (
          <>
            <div className="perf-startup__sep" aria-hidden="true" />
            <div className="perf-phases">
              {allPhases.map((phase, i) => (
                <PhaseRow
                  key={phase.id}
                  phase={phase}
                  onSelect={setSelectedPhase}
                  isLast={i === allPhases.length - 1}
                />
              ))}
            </div>
          </>
        )}
      </Card>

      {selectedPhase && (
        <PhaseModal
          phase={selectedPhase}
          report={report}
          onClose={() => setSelectedPhase(null)}
        />
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// PerformanceTab root
// ---------------------------------------------------------------------------

/**
 * Performance diagnostics tab: shows server startup timing and recent browser
 * performance samples captured via the Performance API.
 */
export default function PerformanceTab() {
  const [subTab, setSubTab] = useState("startup");

  return (
    <div className="perf-tab tab-view">
      <div className="perf-tab__header">
        <div>
          <h2>Performance</h2>
          <p>Runtime diagnostics and startup timing for every module.</p>
        </div>
      </div>

      <div className="coreui-mt-md coreui-mb-lg">
        <CoreUIPillTabs
          tabs={SUBTABS}
          value={subTab}
          onChange={setSubTab}
          ariaLabel="Performance sections"
        />
      </div>

      {subTab === "startup" && <StartupSubtab />}
    </div>
  );
}
