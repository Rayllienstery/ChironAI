import { describe, expect, it, vi, beforeEach } from 'vitest';
import { act, renderHook, waitFor } from '@testing-library/react';
import { useLlmProxyBuildsTab } from './useLlmProxyBuildsTab';

const getLlmProxyBuilds = vi.fn();
const getProviderCatalog = vi.fn();
const getPrompts = vi.fn();
const getModelSettings = vi.fn();
const getRagCollections = vi.fn();
const getPipelinePreview = vi.fn();
const getRagModelSettings = vi.fn();

const putLlmProxyBuilds = vi.fn();

vi.mock('../../services/api', () => ({
  getLlmProxyBuilds: (...args) => getLlmProxyBuilds(...args),
  getProviderCatalog: (...args) => getProviderCatalog(...args),
  getPrompts: (...args) => getPrompts(...args),
  getModelSettings: (...args) => getModelSettings(...args),
  getRagCollections: (...args) => getRagCollections(...args),
  getPipelinePreview: (...args) => getPipelinePreview(...args),
  getRagModelSettings: (...args) => getRagModelSettings(...args),
  previewLlmProxyBuildModel: vi.fn(),
  putLlmProxyBuilds: (...args) => putLlmProxyBuilds(...args),
}));

describe('useLlmProxyBuildsTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getLlmProxyBuilds.mockResolvedValue({ builds: [], openai_models_urls: {} });
    getProviderCatalog.mockResolvedValue({ providers: [{ provider_id: 'ollama', title: 'Ollama' }], models: [] });
    getPrompts.mockResolvedValue({ prompts: [] });
    getModelSettings.mockResolvedValue({});
    getRagCollections.mockResolvedValue({ collections: [{ name: 'ios-docs', points_count: 12 }] });
    getPipelinePreview.mockResolvedValue(null);
    getRagModelSettings.mockResolvedValue({});
    putLlmProxyBuilds.mockImplementation(async (builds) => ({ builds }));
  });

  it('loads Qdrant collections when build editor opens', async () => {
    const { result } = renderHook(() => useLlmProxyBuildsTab({}));

    await waitFor(() => {
      expect(getLlmProxyBuilds).toHaveBeenCalled();
    });

    act(() => {
      result.current.openNew();
    });

    await waitFor(() => {
      expect(getRagCollections).toHaveBeenCalled();
    });
    await waitFor(() => {
      expect(result.current.ragCollections).toEqual([{ name: 'ios-docs', points_count: 12 }]);
    });
  });

  it('openEdit preserves rag_collection on draft', async () => {
    const { result } = renderHook(() => useLlmProxyBuildsTab({}));

    await waitFor(() => {
      expect(getLlmProxyBuilds).toHaveBeenCalled();
    });

    act(() => {
      result.current.openEdit({
        id: 'docs-worker',
        backend: 'dumb',
        provider_id: 'ollama',
        model: 'llama3',
        rag_collection: 'ios-docs',
      });
    });

    await waitFor(() => {
      expect(result.current.editingId).toBe('docs-worker');
      expect(result.current.draft?.rag_collection).toBe('ios-docs');
    });
  });

  it('saveForm persists an edited rag_collection via PUT', async () => {
    getLlmProxyBuilds.mockResolvedValue({
      builds: [
        {
          id: 'docs-worker',
          backend: 'dumb',
          provider_id: 'ollama',
          model: 'llama3',
          rag_collection: '',
        },
      ],
      openai_models_urls: {},
    });

    const { result } = renderHook(() => useLlmProxyBuildsTab({}));

    await waitFor(() => {
      expect(getLlmProxyBuilds).toHaveBeenCalled();
    });

    act(() => {
      result.current.openEdit({
        id: 'docs-worker',
        backend: 'dumb',
        provider_id: 'ollama',
        model: 'llama3',
        rag_collection: '',
      });
    });

    act(() => {
      result.current.setDraft({ ...result.current.draft, rag_collection: 'api-docs' });
    });

    await act(async () => {
      await result.current.saveForm();
    });

    expect(putLlmProxyBuilds).toHaveBeenCalledWith([
      expect.objectContaining({
        id: 'docs-worker',
        rag_collection: 'api-docs',
      }),
    ]);
    await waitFor(() => {
      expect(result.current.draft).toBeNull();
    });
  });
});
