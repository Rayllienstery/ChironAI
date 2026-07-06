import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import LlmProxyWizardSteps from './LlmProxyWizardSteps';
import { CUSTOM_PARAMETER_PREFAB_NOTE, PARAMETER_PREFABS } from './constants';
import { emptyDraft } from './helpers';
import { renderWithProviders } from '../../test/renderWithProviders.jsx';

function createProps(overrides = {}) {
  return {
    wizardStep: 0,
    draft: emptyDraft(),
    setDraft: vi.fn(),
    editingId: null,
    chatProviders: [{ provider_id: 'ollama', title: 'Ollama' }],
    filteredModels: [{ id: 'llama3', name: 'Llama 3' }],
    previewBusy: false,
    previewMsg: '',
    runPreview: vi.fn(),
    applySelectedModelDefaults: vi.fn(),
    parameterPrefabNote: CUSTOM_PARAMETER_PREFAB_NOTE,
    applyParameterPrefab: vi.fn(),
    prompts: [],
    matchingParameterPrefab: null,
    buildModalPipelineData: null,
    buildModalHybrid: null,
    buildModalRerank: null,
    proxyDefaults: {},
    ragCollections: [],
    ...overrides,
  };
}

describe('LlmProxyWizardSteps', () => {
  it('renders basic info step with Check model button', () => {
    renderWithProviders(<LlmProxyWizardSteps {...createProps()} />);
    expect(screen.getByRole('button', { name: /check model/i })).toBeInTheDocument();
    expect(screen.getByText(/name your build/i)).toBeInTheDocument();
  });

  it('calls runPreview when Check model is clicked', () => {
    const props = createProps();
    renderWithProviders(<LlmProxyWizardSteps {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /check model/i }));
    expect(props.runPreview).toHaveBeenCalledOnce();
  });

  it('shows preview message on basic info step', () => {
    renderWithProviders(<LlmProxyWizardSteps {...createProps({ previewMsg: 'Model reachable' })} />);
    expect(screen.getByText('Model reachable')).toBeInTheDocument();
  });

  it('renders parameter prefab buttons on parameters step', () => {
    renderWithProviders(<LlmProxyWizardSteps {...createProps({ wizardStep: 4 })} />);
    for (const prefab of PARAMETER_PREFABS) {
      expect(screen.getByRole('button', { name: prefab.label })).toBeInTheDocument();
    }
  });

  it('calls applyParameterPrefab when a prefab button is clicked', () => {
    const props = createProps({ wizardStep: 4 });
    renderWithProviders(<LlmProxyWizardSteps {...props} />);
    fireEvent.click(screen.getByRole('button', { name: PARAMETER_PREFABS[0].label }));
    expect(props.applyParameterPrefab).toHaveBeenCalledWith(PARAMETER_PREFABS[0]);
  });

  it('renders RAG collection dropdown on RAG step', () => {
    renderWithProviders(
      <LlmProxyWizardSteps
        {...createProps({
          wizardStep: 1,
          draft: { ...emptyDraft(), rag_enabled: true },
          ragCollections: [{ name: 'ios-docs', points_count: 42 }],
        })}
      />,
    );
    expect(screen.getByTestId('build-wizard-rag')).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /ios-docs \(42 vectors\)/i })).toBeInTheDocument();
    expect(screen.getByRole('option', { name: /server default/i })).toBeInTheDocument();
  });

  it('calls setDraft when RAG collection selection changes', () => {
    const setDraft = vi.fn();
    renderWithProviders(
      <LlmProxyWizardSteps
        {...createProps({
          wizardStep: 1,
          draft: { ...emptyDraft(), rag_enabled: true, rag_collection: '' },
          ragCollections: [{ name: 'ios-docs' }, { name: 'api-docs' }],
          setDraft,
        })}
      />,
    );
    fireEvent.change(screen.getByTestId('build-wizard-rag'), {
      target: { value: 'api-docs' },
    });
    expect(setDraft).toHaveBeenCalledWith(expect.objectContaining({ rag_collection: 'api-docs' }));
  });

  it('shows stale collection option when edit value is not in Qdrant list', () => {
    renderWithProviders(
      <LlmProxyWizardSteps
        {...createProps({
          wizardStep: 1,
          draft: { ...emptyDraft(), rag_enabled: true, rag_collection: 'legacy-coll' },
          ragCollections: [{ name: 'ios-docs' }],
        })}
      />,
    );
    expect(screen.getByRole('option', { name: /legacy-coll \(not listed in Qdrant\)/i })).toBeInTheDocument();
  });

  it('shows empty-state hint when no Qdrant collections exist', () => {
    renderWithProviders(
      <LlmProxyWizardSteps
        {...createProps({
          wizardStep: 1,
          draft: { ...emptyDraft(), rag_enabled: true },
          ragCollections: [],
        })}
      />,
    );
    expect(screen.getByRole('option', { name: /no collections \(server default\)/i })).toBeInTheDocument();
    expect(screen.getByText(/No Qdrant collections found/i)).toBeInTheDocument();
  });
});
