import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import LogsTab from './LogsTab.jsx';

vi.mock('../services/api.js', () => ({
  getLogs: vi.fn().mockResolvedValue({ logs: [] }),
  getProxyLogs: vi.fn().mockResolvedValue({ logs: [] }),
  clearLogs: vi.fn().mockResolvedValue({ ok: true }),
  clearProxyLogs: vi.fn().mockResolvedValue({ ok: true }),
  getLlmProxyStatus: vi.fn().mockResolvedValue({ running: true }),
  getProxyTraces: vi.fn().mockResolvedValue({ traces: [] }),
  clearProxyTraces: vi.fn().mockResolvedValue({ ok: true }),
  getProxyTraceDetail: vi.fn().mockResolvedValue({}),
  getRagFusionJournal: vi.fn().mockResolvedValue({ entries: [] }),
}));

vi.mock('../services/logs.js', () => ({
  startLogPolling: vi.fn(),
  stopLogPolling: vi.fn(),
}));

describe('LogsTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Logs heading', () => {
    render(<LogsTab sessionId="test-session" />);
    expect(screen.getByRole('heading', { level: 2, name: /Logs/i })).toBeInTheDocument();
  });
});
