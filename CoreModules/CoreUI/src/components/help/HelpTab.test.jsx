import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import HelpTab from './HelpTab.jsx';

vi.mock('../../services/api.js', () => ({
  getHelpArticles: vi.fn(),
  getHelpArticle: vi.fn(),
  searchHelpArticles: vi.fn(),
}));

vi.mock('../M3LoadingIndicator.jsx', () => ({
  default: () => <div data-testid="help-loading">Loading</div>,
}));

import { getHelpArticle, getHelpArticles } from '../../services/api.js';

describe('HelpTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getHelpArticles.mockResolvedValue({
      articles: [{ slug: 'builds', title: 'LLM Proxy Builds', tags: ['builds'] }],
    });
    getHelpArticle.mockResolvedValue({
      slug: 'builds',
      title: 'LLM Proxy Builds',
      content: '# LLM Proxy Builds\n\nBuild routing body.',
      tags: ['builds'],
    });
  });

  it('forwards an initial slug into HelpViewer', async () => {
    const onConsumed = vi.fn();
    render(<HelpTab initialSlug="builds" onInitialSlugConsumed={onConsumed} />);

    await waitFor(() => {
      expect(getHelpArticle).toHaveBeenCalledWith('builds');
    });
    expect(await screen.findByText(/Build routing body/i)).toBeInTheDocument();
  });
});
