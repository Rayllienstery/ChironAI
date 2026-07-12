import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import LogsTab from './LogsTab.jsx';
import { needsRemoteRevealPin } from '../services/remoteRevealPin.js';

vi.mock('../services/remoteRevealPin.js', async (importOriginal) => {
  const actual = await importOriginal();
  return {
    ...actual,
    needsRemoteRevealPin: vi.fn(() => false),
  };
});

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
    needsRemoteRevealPin.mockReturnValue(false);
  });

  it('renders Logs heading on loopback', () => {
    render(<LogsTab sessionId="test-session" />);
    expect(screen.getByRole('heading', { level: 2, name: /Logs/i })).toBeInTheDocument();
  });

  it('shows remote reveal PIN gate on LAN before logs UI', () => {
    needsRemoteRevealPin.mockReturnValue(true);
    render(<LogsTab sessionId="test-session" />);
    expect(
      screen.getByRole('heading', { level: 2, name: /Remote reveal PIN required/i }),
    ).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2, name: /^Logs$/i })).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Unlock logs/i })).toBeInTheDocument();
  });
});
