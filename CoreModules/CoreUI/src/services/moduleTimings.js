/**
 * Browser-side store for lazy module (chunk) load timings.
 *
 * lazyWithRetry() in App.jsx calls recordModuleLoad() after each dynamic
 * import resolves. PerformanceTab reads getModuleTimings() to display
 * per-module load durations inside the "WebUI (Browser)" phase modal.
 */

const _timings = [];

/** Prettify "DashboardTab" → "Dashboard Tab" */
function humanize(key) {
  return key.replace(/([A-Z])/g, ' $1').trim();
}

/**
 * Record a lazy chunk load.
 * @param {string}  key        - Component key (e.g. "DashboardTab")
 * @param {number}  durationMs - Elapsed milliseconds from import() call to resolution
 * @param {string}  status     - "ok" | "failed"
 */
export function recordModuleLoad(key, durationMs, status = 'ok') {
  _timings.push({
    id: key,
    label: humanize(key),
    duration_ms: Math.round(durationMs),
    status,
    loaded_at: Date.now(),
  });
}

/**
 * Returns a snapshot of all module load timings collected so far.
 * Sorted chronologically (load order).
 */
export function getModuleTimings() {
  return [..._timings].sort((a, b) => a.loaded_at - b.loaded_at);
}
