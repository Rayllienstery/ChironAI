import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import LlmProxyBuildsTab from './LlmProxyBuildsTab.jsx';

vi.mock('../services/api.js', () => ({
  getLlmProxyBuilds: vi.fn().mockResolvedValue({ builds: [], openai_models_urls: {} }),
  getProviderCatalog: vi.fn().mockResolvedValue({ providers: [], models: [] }),
  getPrompts: vi.fn().mockResolvedValue({ prompts: [] }),
  getModelSettings: vi.fn().mockResolvedValue({}),
  getPipelinePreview: vi.fn().mockResolvedValue({}),
  getRagModelSettings: vi.fn().mockResolvedValue({}),
  putLlmProxyBuilds: vi.fn(),
  previewLlmProxyBuildModel: vi.fn(),
}));

describe('LlmProxyBuildsTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders LLM Proxy heading', async () => {
    render(<LlmProxyBuildsTab />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /LLM Proxy/i })).toBeInTheDocument();
    });
  });
});
