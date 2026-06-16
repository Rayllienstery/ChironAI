import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useExtensionRuntimeActions } from './useExtensionRuntimeActions';

const runExtensionTabAction = vi.fn();

vi.mock('../../services/api', () => ({
  runExtensionTabAction: (...args: unknown[]) => runExtensionTabAction(...args),
}));

describe('useExtensionRuntimeActions', () => {
  const confirm = vi.fn(async () => true);
  const load = vi.fn(async () => {});
  const setActionResult = vi.fn();
  const setFieldState = vi.fn((updater) => {
    if (typeof updater === 'function') updater({});
  });

  beforeEach(() => {
    vi.clearAllMocks();
    confirm.mockResolvedValue(true);
    runExtensionTabAction.mockResolvedValue({ ok: true, message: 'done' });
  });

  function renderActions() {
    return renderHook(() => useExtensionRuntimeActions({
      extensionId: 'ollama',
      fieldState: { backend_url: 'http://local' },
      setFieldState,
      setActionResult,
      setActionDetails: vi.fn(),
      setRefreshKey: vi.fn(),
      setBusyActionId: vi.fn(),
      setBusyModelActionKey: vi.fn(),
      setActiveAction: vi.fn(),
      setOpenModelMenuId: vi.fn(),
      setOpenModelMenuPos: vi.fn(),
      setActionTimerNow: vi.fn(),
      load,
      confirm,
      persistExtensionNotification: vi.fn(),
      isRuntimeModelDetailsForModal: () => false,
      normalizeModelDetailsForModal: (details) => details as Record<string, unknown>,
    }));
  }

  it('cancels when confirm is rejected', async () => {
    confirm.mockResolvedValueOnce(false);
    const { result } = renderActions();
    await act(async () => {
      await result.current.handleContentAction({ id: 'stop', confirm: 'Stop?' });
    });
    expect(runExtensionTabAction).not.toHaveBeenCalled();
  });

  it('runs action and reports notification on success', async () => {
    const persist = vi.fn();
    const { result } = renderHook(() => useExtensionRuntimeActions({
      extensionId: 'ollama',
      fieldState: {},
      setFieldState,
      setActionResult,
      setActionDetails: vi.fn(),
      setRefreshKey: vi.fn(),
      setBusyActionId: vi.fn(),
      setBusyModelActionKey: vi.fn(),
      setActiveAction: vi.fn(),
      setOpenModelMenuId: vi.fn(),
      setOpenModelMenuPos: vi.fn(),
      setActionTimerNow: vi.fn(),
      load,
      confirm,
      persistExtensionNotification: persist,
      isRuntimeModelDetailsForModal: () => false,
      normalizeModelDetailsForModal: (details) => details as Record<string, unknown>,
    }));

    await act(async () => {
      await result.current.handleContentAction({ id: 'refresh', label: 'Refresh' });
    });

    expect(runExtensionTabAction).toHaveBeenCalledWith(
      'ollama',
      'refresh',
      {},
      expect.objectContaining({ timeoutMs: 30_000 }),
    );
    expect(persist).toHaveBeenCalled();
    expect(load).toHaveBeenCalledWith(true);
  });

  it('sets action result on autosave error', async () => {
    runExtensionTabAction.mockRejectedValueOnce(new Error('save failed'));
    const { result } = renderActions();
    await act(async () => {
      await result.current.runAutosave('save_backend', 'backend_url');
    });
    expect(setActionResult).toHaveBeenCalledWith({ ok: false, message: 'save failed' });
  });
});
