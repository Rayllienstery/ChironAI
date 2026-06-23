import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import RagTestsTab from './RagTestsTab.jsx';

vi.mock('../services/api.js', () => ({
  getProviderCatalog: vi.fn().mockResolvedValue({ providers: [], models: [] }),
  getPrompts: vi.fn().mockResolvedValue({ prompts: [] }),
  getRagCollections: vi.fn().mockResolvedValue({ collections: [{ name: 'webcrawl' }] }),
  getRagTests: vi.fn().mockResolvedValue({ tests: [], filters: { platform: [], framework: [], difficulty: [] } }),
  getRagTestRunsSummary: vi.fn().mockResolvedValue({ total_runs: 0 }),
  getRagTestRuns: vi.fn().mockResolvedValue({ runs: [] }),
  getProxyTraceCurrent: vi.fn().mockResolvedValue({}),
}));

describe('RagTestsTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders RAG Tests heading', async () => {
    render(
      <RagTestsTab
        running={false}
        results={[]}
        onStartRun={vi.fn()}
        onCancelRun={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /RAG Tests/i })).toBeInTheDocument();
    });
  });
});
