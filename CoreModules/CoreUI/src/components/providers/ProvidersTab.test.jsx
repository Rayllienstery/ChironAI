import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, screen, waitFor } from '@testing-library/react';
import ProvidersTab from './ProvidersTab.jsx';
import { OnboardingProvider } from '../onboarding/OnboardingProvider.jsx';
import { renderWithProviders } from '../../test/renderWithProviders.jsx';

vi.mock('../../services/providers.js', () => ({
  listCustomProviders: vi.fn(),
  createCustomProvider: vi.fn(),
  updateCustomProvider: vi.fn(),
  deleteCustomProvider: vi.fn(),
  testCustomProvider: vi.fn(),
}));

vi.mock('../../services/api.js', () => ({
  getExtensionProviders: vi.fn(),
  getSettings: vi.fn().mockResolvedValue({}),
  updateSettings: vi.fn().mockResolvedValue({ status: 'ok' }),
}));

import { listCustomProviders } from '../../services/providers.js';
import { getExtensionProviders } from '../../services/api.js';

describe('ProvidersTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
    listCustomProviders.mockResolvedValue({
      providers: [
        {
          id: 'my-gateway',
          display_name: 'My Gateway',
          base_url: 'https://api.example.com/v1',
          enabled: true,
          api_key_configured: true,
        },
      ],
    });
    getExtensionProviders.mockResolvedValue({
      providers: [{ provider_id: 'ollama-provider', title: 'Ollama Provider', models: ['llama3'] }],
    });
  });

  it('renders overview card and custom provider rows', async () => {
    renderWithProviders(
      <OnboardingProvider>
        <ProvidersTab onNavigate={vi.fn()} />
      </OnboardingProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('My Gateway')).toBeInTheDocument();
    });
    expect(screen.getByRole('heading', { name: 'Overview' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Add provider' })).toBeInTheDocument();
  });

  it('shows extension providers on the Extensions sub-tab', async () => {
    renderWithProviders(
      <OnboardingProvider>
        <ProvidersTab onNavigate={vi.fn()} />
      </OnboardingProvider>,
    );

    await waitFor(() => {
      expect(screen.getByText('My Gateway')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('tab', { name: 'Extensions' }));

    expect(await screen.findByText('Ollama Provider')).toBeInTheDocument();
  });
});
