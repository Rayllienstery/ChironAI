import { describe, expect, it, vi, beforeEach } from 'vitest';
import { createDefaultOnboardingState, readOnboardingStateFromStorage, writeOnboardingStateToStorage } from './onboardingState.js';

describe('onboardingState', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('returns defaults when storage is empty', () => {
    expect(readOnboardingStateFromStorage()).toEqual(createDefaultOnboardingState());
  });

  it('persists completion flag', () => {
    const saved = writeOnboardingStateToStorage({
      ...createDefaultOnboardingState(),
      firstRunCompleted: true,
    });
    expect(saved.firstRunCompleted).toBe(true);
    expect(readOnboardingStateFromStorage().firstRunCompleted).toBe(true);
  });
});
