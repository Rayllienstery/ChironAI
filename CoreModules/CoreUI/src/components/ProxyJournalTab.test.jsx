import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearProxyJournal, getProxyJournal } from '../services/api.js';
import ProxyJournalTab from './ProxyJournalTab.jsx';

vi.mock('../services/api.js', () => ({
  clearProxyJournal: vi.fn().mockResolvedValue({ ok: true }),
  getProxyJournal: vi.fn().mockResolvedValue({
    logs: [
      {
        id: 7,
        timestamp: '2026-01-01T12:00:00Z',
        message: 'User asked about adapters',
        metadata: {
          trace_id: 'trace-7',
          model: 'gpt-test',
          latency_ms: 42,
          prompt_tokens: 10,
          completion_tokens: 5,
          total_tokens: 15,
        },
      },
    ],
  }),
}));

describe('ProxyJournalTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('loads journal rows and clears persisted history after confirmation', async () => {
    render(<ProxyJournalTab />);

    expect(screen.getByRole('heading', { name: 'RAG Fusion Journal' })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('User asked about adapters')).toBeInTheDocument();
    });
    expect(screen.getByText('trace-7')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Clear DB history' }));

    await waitFor(() => {
      expect(clearProxyJournal).toHaveBeenCalledTimes(1);
    });
    expect(getProxyJournal).toHaveBeenCalled();
  });
});
