import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import DependenciesTab from './DependenciesTab.jsx';

const mockGetDependencies = vi.fn();

vi.mock('../services/api.js', () => ({
  getDependencies: (...args) => mockGetDependencies(...args),
  checkDependencyUpdates: vi.fn(),
  getDependencyJob: vi.fn(),
  updateDependencies: vi.fn(),
}));

describe('DependenciesTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetDependencies.mockResolvedValue({
      dependencies: [],
      counts: { installed: 0, missing: 0, declared: 0 },
    });
  });

  it('renders Dependencies heading', async () => {
    render(<DependenciesTab />);
    expect(screen.getByRole('heading', { level: 1, name: /Dependencies/i })).toBeInTheDocument();
  });

  it('loads inventory on mount', async () => {
    render(<DependenciesTab />);
    await waitFor(() => {
      expect(mockGetDependencies).toHaveBeenCalledOnce();
    });
  });

  it('shows ecosystem filter tabs', async () => {
    render(<DependenciesTab />);
    expect(screen.getByRole('tab', { name: /^Python$/i })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: /CoreUI npm/i })).toBeInTheDocument();
  });
});
