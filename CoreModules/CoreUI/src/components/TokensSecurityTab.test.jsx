import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import TokensSecurityTab from './TokensSecurityTab.jsx';

vi.mock('../services/api.js', () => ({
  getLlmProxyApiKeyStatus: vi.fn().mockResolvedValue({ configured: false, recoverable: false }),
  generateLlmProxyApiKey: vi.fn(),
  deleteLlmProxyApiKey: vi.fn(),
  revealLlmProxyApiKey: vi.fn(),
}));

describe('TokensSecurityTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Tokens and Security heading', async () => {
    render(<TokensSecurityTab />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Tokens and Security/i })).toBeInTheDocument();
    });
  });
});
