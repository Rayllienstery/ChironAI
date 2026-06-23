import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import DashboardTab from '../components/DashboardTab.jsx';

vi.mock('../services/api.js', () => ({
  getLlmProxyStatus: vi.fn().mockResolvedValue({ base_url: 'http://localhost:5000' }),
}));

describe('DashboardTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders ChironAI heading and intro panel', async () => {
    render(<DashboardTab />);
    expect(screen.getByRole('heading', { level: 2, name: /ChironAI/i })).toBeInTheDocument();
    expect(screen.getByText(/Local, model-agnostic RAG layer/i)).toBeInTheDocument();
  });
});
