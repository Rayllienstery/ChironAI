import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { act, render, screen } from '@testing-library/react';
import { OnboardingProvider } from './OnboardingProvider.jsx';
import { createDefaultOnboardingState, writeOnboardingStateToStorage } from './onboardingState.js';

vi.mock('./useContextualTour.js', async () => vi.importActual('./useContextualTour.js'));

vi.mock('../../services/api.js', () => ({
  getSettings: vi.fn().mockResolvedValue({}),
}));

import { useContextualTour } from './useContextualTour.js';

const TOUR_STEPS = [{ id: 'ctx', title: 'Contextual builds', body: 'Per-build RAG collection.' }];

function Harness({ enabled }) {
  useContextualTour('builds', TOUR_STEPS, enabled);
  return <div data-testid="harness" />;
}

describe('useContextualTour', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    window.localStorage.clear();
    writeOnboardingStateToStorage({
      ...createDefaultOnboardingState(),
      firstRunCompleted: true,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts the contextual tour after the debounce when enabled', async () => {
    render(
      <OnboardingProvider>
        <Harness enabled />
      </OnboardingProvider>,
    );

    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    expect(screen.getByRole('dialog', { name: 'Contextual builds' })).toBeInTheDocument();
  });

  it('does not start the tour while disabled', async () => {
    render(
      <OnboardingProvider>
        <Harness enabled={false} />
      </OnboardingProvider>,
    );

    await act(async () => {
      vi.advanceTimersByTime(500);
    });

    expect(screen.queryByRole('dialog', { name: 'Contextual builds' })).not.toBeInTheDocument();
  });
});
