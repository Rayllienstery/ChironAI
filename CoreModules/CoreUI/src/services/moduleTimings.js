/**
 * Browser-side store for lazy module (chunk) load timings.
 *
 * loadTrackedModule() wraps dynamic imports, records both active and completed
 * loads, and keeps the promise cached so prefetch and navigation share work.
 * PerformanceTab reads getModuleTimings() and subscribes to live changes.
 */

const _records = new Map();
const _promises = new Map();
const _listeners = new Set();
const _staleTimers = new Map();

/** Prettify "DashboardTab" -> "Dashboard Tab" */
function humanize(key) {
  return key.replace(/([A-Z])/g, ' $1').trim();
}

function nowMs() {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') {
    return performance.now();
  }
  return Date.now();
}

function notify() {
  _listeners.forEach((listener) => {
    try {
      listener();
    } catch {
      // ignore listener failures
    }
  });
}

function mergeSource(record, source) {
  const value = String(source || 'navigation');
  const sources = Array.isArray(record.sources) ? record.sources : [];
  return sources.includes(value) ? sources : [...sources, value];
}

function createImportTimeoutError(id, timeoutMs) {
  const error = new Error(`Timed out dynamically importing ${id} after ${timeoutMs}ms`);
  error.name = 'ModuleImportTimeoutError';
  return error;
}

function withLoadTimeout(id, promise, timeoutMs, source, startPerfMs) {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) return promise;

  return new Promise((resolve, reject) => {
    let settled = false;
    const timeoutId = window.setTimeout(() => {
      if (settled) return;
      settled = true;
      const error = createImportTimeoutError(id, timeoutMs);
      _promises.delete(id);
      recordModuleLoad(id, nowMs() - startPerfMs, 'failed', {
        source,
        step: 'timed out',
        error,
      });
      reject(error);
    }, timeoutMs);

    promise
      .then((mod) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeoutId);
        resolve(mod);
      })
      .catch((error) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeoutId);
        reject(error);
      });
  });
}

function clearStaleTimer(id) {
  const timerId = _staleTimers.get(id);
  if (timerId != null) {
    window.clearTimeout(timerId);
    _staleTimers.delete(id);
  }
}

function scheduleStaleMarker(id, staleAfterMs, source, startPerfMs) {
  clearStaleTimer(id);
  if (!Number.isFinite(staleAfterMs) || staleAfterMs <= 0) return;

  const timerId = window.setTimeout(() => {
    _staleTimers.delete(id);
    const current = _records.get(id);
    if (!current || current.status !== 'in_progress') return;
    const elapsedMs = Math.max(0, nowMs() - startPerfMs);
    _records.set(id, {
      ...current,
      status: 'skipped',
      step: 'prefetch pending in background',
      sources: mergeSource(current, source),
      duration_ms: Math.round(elapsedMs),
      elapsed_ms: Math.round(elapsedMs),
      loaded_at: Date.now(),
    });
    notify();
  }, staleAfterMs);
  _staleTimers.set(id, timerId);
}

/**
 * Record a lazy chunk load.
 *
 * @param {string} key - Component key (e.g. "DashboardTab")
 * @param {number} durationMs - Elapsed milliseconds from import() call to resolution
 * @param {string} status - "ok" | "failed"
 * @param {object} options - Optional source, step, and error metadata.
 */
export function recordModuleLoad(key, durationMs, status = 'ok', options = {}) {
  const id = String(key);
  const existing = _records.get(id) || {
    id,
    label: humanize(id),
    started_at: Date.now(),
    start_perf_ms: nowMs() - durationMs,
    sources: [],
  };
  const next = {
    ...existing,
    id,
    label: humanize(id),
    duration_ms: Math.round(durationMs),
    elapsed_ms: Math.round(durationMs),
    status,
    step: options.step || (status === 'ok' ? 'resolved' : 'failed'),
    sources: mergeSource(existing, options.source),
    error: options.error ? String(options.error?.message || options.error) : undefined,
    loaded_at: Date.now(),
  };
  _records.set(id, next);
  notify();
  return next;
}

/**
 * Track and cache a dynamic import.
 *
 * When a prefetch is already in flight, navigation reuses the same promise and
 * the Performance tab shows both sources on the same active row.
 */
export function loadTrackedModule(key, importer, options = {}) {
  const id = String(key);
  const source = options.source || 'navigation';
  const timeoutMs = Number.isFinite(options.timeoutMs) ? options.timeoutMs : 20000;
  const staleAfterMs = Number.isFinite(options.staleAfterMs) ? options.staleAfterMs : 0;
  const active = _records.get(id);
  if (_promises.has(id)) {
    if (active) {
      const waitsForModule = timeoutMs > 0;
      if (waitsForModule) clearStaleTimer(id);
      _records.set(id, {
        ...active,
        status: waitsForModule ? 'in_progress' : active.status,
        sources: mergeSource(active, source),
        step: waitsForModule || active.status === 'in_progress'
          ? 'awaiting existing import'
          : active.step,
      });
      notify();
    }
    const existing = _promises.get(id);
    const startPerfMs = active?.start_perf_ms ?? nowMs();
    if (timeoutMs <= 0) {
      scheduleStaleMarker(id, staleAfterMs, source, startPerfMs);
    }
    return withLoadTimeout(id, existing, timeoutMs, source, startPerfMs);
  }

  const startPerfMs = nowMs();
  const startedAt = Date.now();
  _records.set(id, {
    id,
    label: humanize(id),
    status: 'in_progress',
    step: options.step || 'import() requested',
    sources: [source],
    started_at: startedAt,
    start_perf_ms: startPerfMs,
    loaded_at: null,
    duration_ms: null,
    elapsed_ms: 0,
  });
  notify();
  if (timeoutMs <= 0) {
    scheduleStaleMarker(id, staleAfterMs, source, startPerfMs);
  }

  const promise = importer()
    .then((mod) => {
      clearStaleTimer(id);
      recordModuleLoad(id, nowMs() - startPerfMs, 'ok', {
        source,
        step: 'resolved',
      });
      return mod;
    })
    .catch((error) => {
      clearStaleTimer(id);
      _promises.delete(id);
      if (error?.name !== 'ModuleImportTimeoutError') {
        recordModuleLoad(id, nowMs() - startPerfMs, 'failed', {
          source,
          step: 'failed',
          error,
        });
      }
      throw error;
    });

  _promises.set(id, promise);
  return withLoadTimeout(id, promise, timeoutMs, source, startPerfMs);
}

/**
 * Returns a snapshot of all module load timings collected so far.
 * Sorted chronologically by first request time.
 */
export function getModuleTimings() {
  const currentPerfMs = nowMs();
  return [..._records.values()]
    .map((record) => {
      if (record.status !== 'in_progress') return { ...record };
      const elapsedMs = Math.max(0, currentPerfMs - record.start_perf_ms);
      return {
        ...record,
        elapsed_ms: Math.round(elapsedMs),
        duration_ms: Math.round(elapsedMs),
      };
    })
    .sort((a, b) => a.started_at - b.started_at);
}

export function subscribeModuleTimings(listener) {
  if (typeof listener !== 'function') return () => {};
  _listeners.add(listener);
  return () => _listeners.delete(listener);
}
