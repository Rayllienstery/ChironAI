import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getExtensionTab, runExtensionTabAction } from '../services/api.js';
import ExtensionRuntimeTab from './ExtensionRuntimeTab.jsx';

vi.mock('../services/api.js', () => ({
  getExtensionTab: vi.fn().mockResolvedValue({
    load_state: { status: 'ready', cached_at: '2026-01-01T00:00:00Z' },
    content: {
      type: 'iframe',
      title: 'Ollama Runtime',
      src: 'http://127.0.0.1:11434',
      fields: [
        {
          key: 'backend_url',
          label: 'Backend URL',
          value: 'http://127.0.0.1:11434',
          autosave_action_id: 'save_backend',
        },
      ],
      actions: [{ id: 'refresh', label: 'Refresh runtime' }],
      details: [{ label: 'Provider', value: 'Ollama' }],
    },
  }),
  refreshExtensionTab: vi.fn().mockResolvedValue({ ok: true }),
  runExtensionTabAction: vi.fn().mockResolvedValue({ ok: true, message: 'Refreshed' }),
}));

describe('ExtensionRuntimeTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders extension iframe content and runs content actions', async () => {
    render(<ExtensionRuntimeTab extensionId="ollama" title="Ollama" />);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Ollama Runtime' })).toBeInTheDocument();
    });
    expect(screen.getByLabelText('Backend URL')).toHaveValue('http://127.0.0.1:11434');
    expect(screen.getByText('Ollama')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /Refresh runtime/i }));

    await waitFor(() => {
      expect(runExtensionTabAction).toHaveBeenCalledWith(
        'ollama',
        'refresh',
        {},
        expect.objectContaining({ timeoutMs: expect.any(Number) }),
      );
    });
    expect(getExtensionTab).toHaveBeenCalledWith('ollama');
  });
});
