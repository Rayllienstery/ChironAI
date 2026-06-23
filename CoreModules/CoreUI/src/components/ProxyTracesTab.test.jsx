import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearProxyTraces, getLlmProxyStatus, getProxyTraces } from '../services/api.js';
import ProxyTracesTab from './ProxyTracesTab.jsx';

vi.mock('../services/api.js', () => ({
  clearProxyTraces: vi.fn().mockResolvedValue({ ok: true }),
  getLlmProxyStatus: vi.fn().mockResolvedValue({ enabled: true }),
  getProxyTraces: vi.fn().mockResolvedValue({
    traces: [
      {
        trace_id: 'trace-live-1',
        timestamp: '2026-01-01T12:00:00Z',
        user_query: 'Trace query',
        resolved_model: 'gpt-test',
        elapsed_ms: 33,
        step_count: 2,
      },
    ],
  }),
}));

describe('ProxyTracesTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('renders trace buffers and clears live traces after confirmation', async () => {
    render(<ProxyTracesTab />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Traces' })).toBeInTheDocument();
    });
    expect(screen.getAllByText('Trace query').length).toBeGreaterThan(0);
    expect(screen.getAllByText('trace-live-1').length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('button', { name: 'Clear trace buffer' }));

    await waitFor(() => {
      expect(clearProxyTraces).toHaveBeenCalledTimes(1);
    });
    expect(getLlmProxyStatus).toHaveBeenCalled();
    expect(getProxyTraces).toHaveBeenCalled();
  });
});
