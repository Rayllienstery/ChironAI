import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ExtensionRuntimeTab from './ExtensionRuntimeTab.jsx';

vi.mock('../services/api.js', () => ({
  getExtensionTab: vi.fn().mockResolvedValue({
    load_state: { status: 'ready', cached_at: '2026-01-01T00:00:00Z' },
    schema: {
      pages: [{
        id: 'main',
        sections: [{
          id: 'status',
          title: 'Status',
          components: [{ type: 'text', key: 'hello', label: 'Hello', value: 'world' }],
        }],
      }],
    },
  }),
  refreshExtensionTab: vi.fn().mockResolvedValue({ ok: true }),
  runExtensionTabAction: vi.fn(),
}));

describe('ExtensionRuntimeTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders schema section after load', async () => {
    render(<ExtensionRuntimeTab extensionId="ollama" title="Ollama" />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Status' })).toBeInTheDocument();
      expect(screen.getByText('world')).toBeInTheDocument();
    });
  });
});
