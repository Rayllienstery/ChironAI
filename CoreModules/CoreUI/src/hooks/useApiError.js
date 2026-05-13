import { useState } from 'react';

/**
 * Centralized error state management for API calls.
 *
 * Handles both the legacy string error format `{"error": "message"}` and the
 * structured format `{"error": {"code": "...", "message": "..."}}` produced by
 * the ErrorManager CoreModule.
 *
 * Usage:
 *   const { error, clearError, wrap } = useApiError();
 *
 *   // wrap() clears the previous error, calls fn, and captures any thrown Error:
 *   await wrap(async () => {
 *     const data = await saveSomething();
 *     setResult(data);
 *   });
 *
 *   // Show the error in JSX:
 *   {error && <div className="api-error">{error}</div>}
 */
export function useApiError() {
  const [error, setError] = useState(null);

  const clearError = () => setError(null);

  const handleError = (e) => {
    setError(e?.message ?? String(e));
  };

  /**
   * Execute an async function, clearing the previous error first.
   * Captures thrown errors into `error` state.  Rethrows by default so the
   * caller can also react to the failure (e.g. skip a navigation step).
   *
   * @param {() => Promise<any>} fn
   * @param {{ rethrow?: boolean }} opts
   */
  const wrap = async (fn, { rethrow = true } = {}) => {
    clearError();
    try {
      return await fn();
    } catch (e) {
      handleError(e);
      if (rethrow) throw e;
    }
  };

  return { error, setError, clearError, handleError, wrap };
}
