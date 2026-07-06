import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import LlmProxyBuildsTab from './LlmProxyBuildsTab.jsx';
import { renderWithProviders } from '../test/renderWithProviders.jsx';

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
    renderWithProviders(<LlmProxyBuildsTab />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /LLM Proxy/i })).toBeInTheDocument();
    });
  });

  it('opens new build wizard without crashing', async () => {
    renderWithProviders(<LlmProxyBuildsTab />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new build/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /new build/i }));
    await waitFor(() => {
      expect(screen.getByText('Create new build')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /check model/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /save build/i })).toBeInTheDocument();
    });
  });

  it('navigates wizard to parameters step and renders prefab buttons', async () => {
    renderWithProviders(<LlmProxyBuildsTab />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /new build/i })).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', { name: /new build/i }));
    await waitFor(() => {
      expect(screen.getByText('Create new build')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('tab', { name: /step 5: parameters/i }));
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^light$/i })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /^medium$/i })).toBeInTheDocument();
    });
  });
});
