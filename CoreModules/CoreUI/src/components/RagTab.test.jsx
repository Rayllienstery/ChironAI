import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import RagTab from '../components/RagTab.jsx';

vi.mock('../services/api.js', () => ({
  getRagStatus: vi.fn().mockResolvedValue({ running: false }),
  getRagCollections: vi.fn().mockResolvedValue({ collections: [] }),
  getRagKeywordCollections: vi.fn().mockResolvedValue({ collections: [] }),
  getRagTriggerSettings: vi.fn().mockResolvedValue({ threshold: 5 }),
  getRagFrameworkSettings: vi.fn().mockResolvedValue({}),
  getProviderCatalog: vi.fn().mockResolvedValue({ providers: [], models: [] }),
  getRagModelSettings: vi.fn().mockResolvedValue({}),
  getModelSettings: vi.fn().mockResolvedValue({}),
  startRag: vi.fn(),
  stopRag: vi.fn(),
  updateRagTriggerSettings: vi.fn(),
  updateRagFrameworkSettings: vi.fn(),
  updateRagModelSettings: vi.fn(),
  updateModelSettings: vi.fn(),
  saveRagKeywordCollections: vi.fn(),
  deleteRagKeywordCollection: vi.fn(),
  checkRagTrigger: vi.fn(),
}));

vi.mock('../hooks/useMergedPipelinePreview.js', () => ({
  useMergedPipelinePreview: () => ({ preview: null, loading: false, error: null }),
}));

describe('RagTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders RAG heading', async () => {
    render(<RagTab />);
    expect(screen.getByRole('heading', { level: 2, name: /RAG/i })).toBeInTheDocument();
  });
});
