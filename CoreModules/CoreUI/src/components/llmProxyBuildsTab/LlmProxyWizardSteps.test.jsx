import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import LlmProxyWizardSteps from './LlmProxyWizardSteps';
import { CUSTOM_PARAMETER_PREFAB_NOTE, PARAMETER_PREFABS } from './constants';
import { emptyDraft } from './helpers';

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
    ...overrides,
  };
}

describe('LlmProxyWizardSteps', () => {
  it('renders basic info step with Check model button', () => {
    render(<LlmProxyWizardSteps {...createProps()} />);
    expect(screen.getByRole('button', { name: /check model/i })).toBeInTheDocument();
    expect(screen.getByText(/name your build/i)).toBeInTheDocument();
  });

  it('calls runPreview when Check model is clicked', () => {
    const props = createProps();
    render(<LlmProxyWizardSteps {...props} />);
    fireEvent.click(screen.getByRole('button', { name: /check model/i }));
    expect(props.runPreview).toHaveBeenCalledOnce();
  });

  it('shows preview message on basic info step', () => {
    render(<LlmProxyWizardSteps {...createProps({ previewMsg: 'Model reachable' })} />);
    expect(screen.getByText('Model reachable')).toBeInTheDocument();
  });

  it('renders parameter prefab buttons on parameters step', () => {
    render(<LlmProxyWizardSteps {...createProps({ wizardStep: 4 })} />);
    for (const prefab of PARAMETER_PREFABS) {
      expect(screen.getByRole('button', { name: prefab.label })).toBeInTheDocument();
    }
  });

  it('calls applyParameterPrefab when a prefab button is clicked', () => {
    const props = createProps({ wizardStep: 4 });
    render(<LlmProxyWizardSteps {...props} />);
    fireEvent.click(screen.getByRole('button', { name: PARAMETER_PREFABS[0].label }));
    expect(props.applyParameterPrefab).toHaveBeenCalledWith(PARAMETER_PREFABS[0]);
  });
});
