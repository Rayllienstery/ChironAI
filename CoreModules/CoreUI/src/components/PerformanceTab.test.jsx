import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import PerformanceTab from './PerformanceTab.jsx';

vi.mock('../services/api.js', () => ({
  getStartupPerformance: vi.fn().mockResolvedValue({ modules: [], total_ms: 0 }),
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
