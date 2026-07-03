import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { clearProxyJournal, getProxyJournal } from '../services/api.js';
import ProxyJournalTab from './ProxyJournalTab.jsx';

function makeRow(id, userQuery, extraMeta = {}) {
  return {
    id,
    timestamp: '2026-01-01T12:00:00Z',
    message: userQuery,
    metadata: {
      trace_id: `trace-${id}`,
      user_query: userQuery,
      model: 'gpt-test',
      latency_ms: 42,
      prompt_tokens: 10,
      completion_tokens: 5,
      total_tokens: 15,
      ...extraMeta,
    },
  };
}

vi.mock('../services/api.js', () => ({
  clearProxyJournal: vi.fn().mockResolvedValue({ ok: true }),
  getProxyJournal: vi.fn(),
}));

describe('ProxyJournalTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
    getProxyJournal.mockResolvedValue({
      ok: true,
      logs: [makeRow(7, 'User asked about adapters')],
      total: 1,
      offset: 0,
      limit: 50,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
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

  it('shows one grouped row with agent step count for the same trace chain', async () => {
    getProxyJournal.mockResolvedValue({
      ok: true,
      logs: [makeRow(2, 'identical prompt', { trace_chain_id: 'chain-a', agent_step_count: 70 })],
      total: 1,
      offset: 0,
      limit: 50,
    });

    render(<ProxyJournalTab />);

    await waitFor(() => {
      expect(screen.getAllByText('identical prompt')).toHaveLength(1);
    });
    expect(screen.getByText('70 agent steps')).toBeInTheDocument();
    expect(screen.getByText('trace-2')).toBeInTheDocument();
  });

  it('shows separate rows for the same prompt on different trace chains', async () => {
    getProxyJournal.mockResolvedValue({
      ok: true,
      logs: [
        makeRow(2, 'identical prompt', { trace_chain_id: 'chain-a', agent_step_count: 1 }),
        makeRow(1, 'identical prompt', { trace_chain_id: 'chain-b', agent_step_count: 1 }),
      ],
      total: 2,
      offset: 0,
      limit: 50,
    });

    render(<ProxyJournalTab />);

    await waitFor(() => {
      expect(screen.getAllByText('identical prompt')).toHaveLength(2);
    });
    expect(screen.getByText('trace-2')).toBeInTheDocument();
    expect(screen.getByText('trace-1')).toBeInTheDocument();
    expect(screen.queryByText(/agent steps/)).not.toBeInTheDocument();
  });

  it('paginates journal rows with next page fetch', async () => {
    const page1 = Array.from({ length: 50 }, (_, index) =>
      makeRow(100 - index, `Query ${index}`, { trace_chain_id: `chain-${index}` }),
    );
    const page2 = [makeRow(40, 'Older row', { trace_chain_id: 'chain-old' })];

    getProxyJournal.mockImplementation(({ offset = 0 } = {}) => {
      if (offset === 0) {
        return Promise.resolve({ ok: true, logs: page1, total: 60, offset: 0, limit: 50 });
      }
      return Promise.resolve({ ok: true, logs: page2, total: 60, offset: 50, limit: 50 });
    });

    render(<ProxyJournalTab />);

    await waitFor(() => {
      expect(screen.getByText('Query 0')).toBeInTheDocument();
    });
    expect(screen.getByText(/Page 1 of 2/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => {
      expect(screen.getByText('Older row')).toBeInTheDocument();
    });
    expect(getProxyJournal).toHaveBeenCalledWith(expect.objectContaining({ offset: 50, limit: 50 }));
    expect(screen.getByText(/Page 2 of 2/)).toBeInTheDocument();
  });

  it('loads page 2 with offset instead of since_id', async () => {
    const page1 = Array.from({ length: 50 }, (_, index) =>
      makeRow(100 - index, `Query ${index}`, { trace_chain_id: `chain-${index}` }),
    );
    const page2 = [makeRow(40, 'Older row', { trace_chain_id: 'chain-old' })];

    getProxyJournal.mockImplementation(({ offset = 0, since_id } = {}) => {
      if (since_id != null) {
        return Promise.resolve({ ok: true, logs: [] });
      }
      if (offset === 0) {
        return Promise.resolve({ ok: true, logs: page1, total: 51, offset: 0, limit: 50 });
      }
      return Promise.resolve({ ok: true, logs: page2, total: 51, offset: 50, limit: 50 });
    });

    render(<ProxyJournalTab />);

    await waitFor(() => {
      expect(screen.getByText('Query 0')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Next' }));

    await waitFor(() => {
      expect(screen.getByText('Older row')).toBeInTheDocument();
    });

    const page2Calls = getProxyJournal.mock.calls.filter((call) => call[0]?.offset === 50);
    expect(page2Calls.length).toBeGreaterThan(0);
    expect(page2Calls.every((call) => call[0]?.since_id == null)).toBe(true);
  });
});
