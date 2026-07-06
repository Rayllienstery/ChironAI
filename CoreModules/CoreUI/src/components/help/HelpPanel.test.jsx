import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import HelpPanel from './HelpPanel.jsx';

vi.mock('../../services/api.js', () => ({
  getHelpArticle: vi.fn(),
}));

vi.mock('../M3LoadingIndicator.jsx', () => ({
  default: () => <div data-testid="help-panel-loading">Loading</div>,
}));

import { getHelpArticle } from '../../services/api.js';

describe('HelpPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getHelpArticle.mockResolvedValue({
      slug: 'builds',
      title: 'LLM Proxy Builds',
      content: '# LLM Proxy Builds\n\nBody copy.',
    });
  });

  it('loads article content and supports open in Help tab', async () => {
    const onOpenFullHelp = vi.fn();
    const onClose = vi.fn();

    render(
      <HelpPanel
        open
        slug="builds"
        anchor="generation-params"
        label="Temperature"
        onClose={onClose}
        onOpenFullHelp={onOpenFullHelp}
      />,
    );

    await waitFor(() => {
      expect(getHelpArticle).toHaveBeenCalledWith('builds');
    });

    expect(await screen.findByText(/Body copy/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: /open in help tab/i }));
    expect(onOpenFullHelp).toHaveBeenCalledWith('builds', 'generation-params');
    expect(onClose).toHaveBeenCalled();
  });
});
