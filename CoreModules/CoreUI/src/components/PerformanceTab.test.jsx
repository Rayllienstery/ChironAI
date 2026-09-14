import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import PerformanceTab from './PerformanceTab.jsx';

vi.mock('../services/api.js', () => ({
  getStartupPerformance: vi.fn().mockResolvedValue({ modules: [], total_ms: 0 }),
  getPerformanceSnapshot: vi.fn().mockResolvedValue({
    memory: { used_gb: 16, total_gb: 32, used_pct: 50, available_gb: 16 },
    app: { gb: 1.9, host_gb: 0.7, containers_gb: 1.2, bytes: 1, host_bytes: 1, containers_bytes: 1 },
    gpu: null,
    processes: [],
  }),
}));

vi.mock('../services/moduleTimings.js', () => ({
  getModuleTimings: vi.fn(() => []),
  subscribeModuleTimings: vi.fn(() => () => {}),
}));

describe('PerformanceTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Performance heading', async () => {
    render(<PerformanceTab />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Performance/i })).toBeInTheDocument();
    });
  });
});
