import { describe, expect, it, vi } from 'vitest';
import { getModuleTimings, loadTrackedModule } from '../services/moduleTimings.js';

describe('moduleTimings', () => {
  it('records successful dynamic import', async () => {
    const mod = await loadTrackedModule('TestTab', () => Promise.resolve({ default: {} }), {
      timeoutMs: 5000,
    });
    expect(mod).toBeTruthy();
    const rows = getModuleTimings();
    expect(rows.some((r) => r.id === 'TestTab' && r.status === 'ok')).toBe(true);
  });

  it('records failed dynamic import', async () => {
    await expect(
      loadTrackedModule('FailTab', () => Promise.reject(new Error('boom')), { timeoutMs: 5000 }),
    ).rejects.toThrow('boom');
    const rows = getModuleTimings();
    expect(rows.some((r) => r.id === 'FailTab' && r.status === 'failed')).toBe(true);
  });

  it('does not reuse a stale background prefetch for navigation', async () => {
    vi.useFakeTimers();
    try {
      const prefetchImporter = vi.fn(() => new Promise(() => {}));
      const navigationImporter = vi.fn(() => Promise.resolve({ default: {} }));

      loadTrackedModule('StalePrefetchTab', prefetchImporter, {
        source: 'idle prefetch',
        timeoutMs: 0,
        staleAfterMs: 100,
      }).catch(() => {});

      await vi.advanceTimersByTimeAsync(101);
      expect(getModuleTimings().find((row) => row.id === 'StalePrefetchTab')?.status).toBe('skipped');

      await loadTrackedModule('StalePrefetchTab', navigationImporter, {
        source: 'navigation',
        timeoutMs: 5000,
      });

      expect(navigationImporter).toHaveBeenCalledTimes(1);
      expect(getModuleTimings().find((row) => row.id === 'StalePrefetchTab')?.status).toBe('ok');
    } finally {
      vi.useRealTimers();
    }
  });
});
