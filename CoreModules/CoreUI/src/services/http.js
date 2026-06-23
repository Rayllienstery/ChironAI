/** Must match Python ``core.contracts.webui_api.WEBUI_URL_PREFIX``. */
export const API_BASE = '/api/webui';

export const COREUI_SESSION_STORAGE_KEY = 'chironai_coreui_session_id';

/**
 * Extract a human-readable error message from a JSON response body.
 *
 * @param {object | null | undefined} data
 * @param {string} [fallback]
 * @returns {string}
 */
export function extractApiError(data, fallback = 'An error occurred') {
  if (!data) return fallback;
  const err = data.error;
  if (!err) return fallback;
  if (typeof err === 'object') return err.message ?? JSON.stringify(err);
  return String(err);
}

/**
 * @param {string} url
 * @param {{ timeoutMs?: number, fetchOptions?: RequestInit }} [options]
 */
export async function fetchJsonWithTimeout(url, options = {}) {
  const timeoutMs = typeof options.timeoutMs === 'number' ? options.timeoutMs : 0;
  const controller = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const signal = controller ? controller.signal : undefined;
  const fetchOptions = { ...(options.fetchOptions || {}), ...(signal ? { signal } : {}) };

  let timerId = null;
  if (controller && timeoutMs > 0) {
    timerId = window.setTimeout(() => controller.abort(), timeoutMs);
  }
  try {
    const response = await fetch(url, fetchOptions);
    const data = await response.json().catch(() => ({}));
    return { response, data };
  } catch (e) {
    const msg = String(e?.message || e);
    const isAbort = msg.toLowerCase().includes('abort');
    if (isAbort && timeoutMs > 0) {
      throw new Error(`Request timed out after ${timeoutMs}ms`);
    }
    throw e;
  } finally {
    if (timerId != null) window.clearTimeout(timerId);
  }
}
