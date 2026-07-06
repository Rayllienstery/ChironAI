import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import LlmProxyBuildsListPanel from './LlmProxyBuildsListPanel.jsx';
import { HelpPanelProvider } from '../help/HelpPanelContext.jsx';

vi.mock('../help/HelpPanel.jsx', () => ({
  default: ({ open, slug }) => (open ? <div data-testid="help-panel">{slug}</div> : null),
}));

const baseProps = {
  urls: {},
  err: '',
  saving: false,
  load: vi.fn(),
  openNew: vi.fn(),
  draft: null,
  builds: [
    {
      id: 'demo-build',
      display_name: 'Demo',
      provider_id: 'ollama',
      model: 'llama3',
      rag_enabled: true,
      rag_collection: 'docs',
      temperature: '0.2',
    },
  ],
  rowBusy: {},
  detailId: null,
  openDetails: vi.fn(),
  closeDetails: vi.fn(),
  openEdit: vi.fn(),
  openDetailModal: vi.fn(),
  deleteBuild: vi.fn(),
  setOpenMenuModel: vi.fn(),
  openMenuModel: null,
  modelMenuRootRef: { current: null },
  detailModalBuild: null,
  closeDetailModal: vi.fn(),
};

function renderPanel(overrides = {}) {
  return render(
    <HelpPanelProvider>
      <LlmProxyBuildsListPanel {...baseProps} {...overrides} />
    </HelpPanelProvider>,
  );
}

describe('LlmProxyBuildsListPanel', () => {
  it('shows contextual help on the builds list header', () => {
    renderPanel();
    fireEvent.click(screen.getByRole('button', { name: 'Help: LLM Proxy Builds' }));
    expect(screen.getByTestId('help-panel')).toHaveTextContent('builds');
  });

  it('shows field help in the detail modal', () => {
    renderPanel({ detailModalBuild: baseProps.builds[0] });
    fireEvent.click(screen.getByRole('button', { name: 'Help: Coll' }));
    expect(screen.getByTestId('help-panel')).toHaveTextContent('rag-collections');
  });
});
