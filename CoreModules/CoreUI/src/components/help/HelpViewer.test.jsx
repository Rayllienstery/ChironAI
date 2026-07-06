import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import HelpViewer from './HelpViewer.jsx';

vi.mock('../../services/api.js', () => ({
  getHelpArticles: vi.fn(),
  getHelpArticle: vi.fn(),
  searchHelpArticles: vi.fn(),
}));

vi.mock('../M3LoadingIndicator.jsx', () => ({
  default: () => <div data-testid="help-loading">Loading</div>,
}));

import { getHelpArticle, getHelpArticles, searchHelpArticles } from '../../services/api.js';

const INDEX = {
  articles: [
    { slug: 'getting-started', title: 'Getting Started', tags: ['intro'] },
    { slug: 'builds', title: 'LLM Proxy Builds', tags: ['builds'] },
  ],
};

describe('HelpViewer', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getHelpArticles.mockResolvedValue(INDEX);
    getHelpArticle.mockImplementation(async (slug) => ({
      slug,
      title: slug === 'builds' ? 'LLM Proxy Builds' : 'Getting Started',
      tags: slug === 'builds' ? ['builds'] : ['intro'],
      content:
        slug === 'builds'
          ? '# LLM Proxy Builds\n\nBody for builds.'
          : '# Getting Started\n\nBody for getting-started.',
    }));
    searchHelpArticles.mockResolvedValue({
      query: 'builds',
      results: [{ slug: 'builds', title: 'LLM Proxy Builds', snippet: 'Build routing…' }],
    });
  });

  it('loads the index and first article by default', async () => {
    render(<HelpViewer />);

    expect(await screen.findByRole('heading', { level: 1, name: 'Help' })).toBeInTheDocument();
    await waitFor(() => {
      expect(getHelpArticle).toHaveBeenCalledWith('getting-started');
    });
    expect(
      await screen.findByRole('heading', { level: 2, name: 'Getting Started' }),
    ).toBeInTheDocument();
    expect(await screen.findByText(/Body for getting-started/i)).toBeInTheDocument();
  });

  it('switches articles from the navigation list', async () => {
    render(<HelpViewer />);
    await screen.findByRole('heading', { level: 2, name: 'Getting Started' });

    fireEvent.click(screen.getByRole('button', { name: /LLM Proxy Builds/i }));

    await waitFor(() => {
      expect(getHelpArticle).toHaveBeenCalledWith('builds');
    });
    expect(screen.getByText(/Body for builds/i)).toBeInTheDocument();
  });

  it('opens an initial deep-link slug', async () => {
    render(<HelpViewer initialSlug="builds" onInitialSlugConsumed={vi.fn()} />);

    await waitFor(() => {
      expect(getHelpArticle).toHaveBeenCalledWith('builds');
    });
    expect(screen.getByText(/Body for builds/i)).toBeInTheDocument();
  });

  it('shows search matches and navigates to a result', async () => {
    render(<HelpViewer />);
    await screen.findByRole('heading', { level: 2, name: 'Getting Started' });

    fireEvent.change(screen.getByLabelText(/search help articles/i), { target: { value: 'builds' } });

    await waitFor(() => {
      expect(searchHelpArticles).toHaveBeenCalledWith('builds');
    });

    fireEvent.click(await screen.findByRole('button', { name: /Build routing/i }));

    await waitFor(() => {
      expect(getHelpArticle).toHaveBeenCalledWith('builds');
    });
  });

  it('toggles the topics menu on desktop', async () => {
    render(<HelpViewer />);
    await screen.findByRole('heading', { level: 2, name: 'Getting Started' });

    const toggle = screen.getByRole('button', { name: 'Hide topics menu' });
    expect(toggle).toHaveAttribute('aria-expanded', 'true');

    fireEvent.click(toggle);

    expect(screen.getByRole('button', { name: 'Show topics menu' })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });
});
