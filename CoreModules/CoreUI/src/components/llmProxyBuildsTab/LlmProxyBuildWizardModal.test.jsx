import { describe, expect, it, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import LlmProxyBuildWizardModal from './LlmProxyBuildWizardModal';
import { CUSTOM_PARAMETER_PREFAB_NOTE } from './constants';
import { emptyDraft } from './helpers';
import { renderWithProviders } from '../../test/renderWithProviders.jsx';

function createProps(overrides = {}) {
  return {
    draft: emptyDraft(),
    editingId: null,
    closeForm: vi.fn(),
    wizardStep: 0,
    setWizardStep: vi.fn(),
    wizardDirection: 'forward',
    setWizardDirection: vi.fn(),
    saving: false,
    saveForm: vi.fn(),
    setDraft: vi.fn(),
    chatProviders: [],
    filteredModels: [],
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

describe('LlmProxyBuildWizardModal', () => {
  it('renders nothing when draft is null', () => {
    const { container } = renderWithProviders(<LlmProxyBuildWizardModal {...createProps({ draft: null })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it('renders create build modal with wizard navigation buttons', () => {
    renderWithProviders(<LlmProxyBuildWizardModal {...createProps()} />);
    expect(screen.getByText('Create new build')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save build/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /next/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /check model/i })).toBeInTheDocument();
  });

  it('shows edit title when editing an existing build', () => {
    renderWithProviders(<LlmProxyBuildWizardModal {...createProps({ editingId: 'dev-build' })} />);
    expect(screen.getByText('Edit build: dev-build')).toBeInTheDocument();
  });

  it('shows Back button after advancing wizard step', () => {
    renderWithProviders(<LlmProxyBuildWizardModal {...createProps({ wizardStep: 1 })} />);
    expect(screen.getByRole('button', { name: /back/i })).toBeInTheDocument();
  });

  it('advances wizard step when Next is clicked', () => {
    const setWizardStep = vi.fn();
    const setWizardDirection = vi.fn();
    renderWithProviders(
      <LlmProxyBuildWizardModal
        {...createProps({ wizardStep: 0, setWizardStep, setWizardDirection })}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /next/i }));
    expect(setWizardStep).toHaveBeenCalledWith(1);
    expect(setWizardDirection).toHaveBeenCalledWith('forward');
  });
});
