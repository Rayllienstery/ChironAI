import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import LlmProxyTab from './LlmProxyTab.jsx';

vi.mock('../services/api.js', () => ({
  getLlmProxyStatus: vi.fn().mockResolvedValue({ base_url: 'http://localhost:5000', running: true }),
}));

describe('LlmProxyTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders RAG Fusion Proxy heading', async () => {
    render(<LlmProxyTab />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /RAG Fusion Proxy/i })).toBeInTheDocument();
    });
  });
});
