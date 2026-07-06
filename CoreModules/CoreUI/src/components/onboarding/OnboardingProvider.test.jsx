import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { OnboardingProvider, useOnboarding } from './OnboardingProvider.jsx';
import { createDefaultOnboardingState, writeOnboardingStateToStorage } from './onboardingState.js';

vi.mock('../../services/api.js', () => ({
  getSettings: vi.fn().mockResolvedValue({}),
}));

function ContextualStarter() {
  const { maybeStartContextualTour } = useOnboarding();
  return (
    <button
      type="button"
      onClick={() =>
        maybeStartContextualTour('builds', [{ id: 'build-tour', title: 'Build tour', body: 'Wizard help.' }])
      }
    >
      Start builds tour
    </button>
  );
}

describe('OnboardingProvider', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
  });

  it('opens the first-run tour when onboarding is incomplete', async () => {
    writeOnboardingStateToStorage(createDefaultOnboardingState());

    render(
      <OnboardingProvider>
        <div />
      </OnboardingProvider>,
    );

    expect(await screen.findByRole('dialog', { name: 'Welcome to ChironAI' })).toBeInTheDocument();
  });

  it('starts a contextual tour after first-run completion', async () => {
    writeOnboardingStateToStorage({
      ...createDefaultOnboardingState(),
      firstRunCompleted: true,
    });

    render(
      <OnboardingProvider>
        <ContextualStarter />
      </OnboardingProvider>,
    );

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Welcome to ChironAI' })).not.toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: 'Start builds tour' }));

    expect(await screen.findByRole('dialog', { name: 'Build tour' })).toBeInTheDocument();
  });

  it('does not restart a contextual tour that is already completed', async () => {
    writeOnboardingStateToStorage({
      ...createDefaultOnboardingState(),
      firstRunCompleted: true,
      tours: { ...createDefaultOnboardingState().tours, builds: true },
    });

    render(
      <OnboardingProvider>
        <ContextualStarter />
      </OnboardingProvider>,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Start builds tour' }));

    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: 'Build tour' })).not.toBeInTheDocument();
    });
  });
});
