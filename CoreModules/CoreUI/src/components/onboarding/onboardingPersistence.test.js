import { describe, expect, it, beforeEach, vi } from 'vitest';
import { markFirstRunCompleted, markTourCompleted, isTourCompleted } from './onboardingPersistence.js';
import { readOnboardingStateFromStorage } from './onboardingState.js';

vi.mock('../../services/api.js', () => ({
  updateSettings: vi.fn().mockResolvedValue({ status: 'ok' }),
}));

describe('onboardingPersistence', () => {
  beforeEach(() => {
    window.localStorage.clear();
    vi.clearAllMocks();
  });

  it('marks individual contextual tours complete', () => {
    markFirstRunCompleted();
    expect(isTourCompleted('builds')).toBe(false);
    markTourCompleted('builds');
    expect(isTourCompleted('builds')).toBe(true);
    expect(readOnboardingStateFromStorage().tours.builds).toBe(true);
  });
});
