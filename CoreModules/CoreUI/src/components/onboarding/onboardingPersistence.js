import {
  ONBOARDING_SETTINGS_KEY,
  readOnboardingStateFromStorage,
  serializeOnboardingStateForSettings,
  writeOnboardingStateToStorage,
} from './onboardingState.js';
import { updateSettings } from '../../services/api.js';

export function isTourCompleted(tourKey, state = readOnboardingStateFromStorage()) {
  return Boolean(state?.tours?.[tourKey]);
}

export function markTourCompleted(tourKey) {
  const current = readOnboardingStateFromStorage();
  const next = writeOnboardingStateToStorage({
    ...current,
    tours: {
      ...current.tours,
      [tourKey]: true,
    },
  });
  syncOnboardingState(next);
  return next;
}

export function markFirstRunCompleted() {
  const next = writeOnboardingStateToStorage({
    ...readOnboardingStateFromStorage(),
    firstRunCompleted: true,
  });
  syncOnboardingState(next);
  return next;
}

export function syncOnboardingState(state) {
  void updateSettings({
    [ONBOARDING_SETTINGS_KEY]: serializeOnboardingStateForSettings(state),
  }).catch(() => {
    /* localStorage remains the fallback */
  });
}

export function resetFirstRunTour() {
  const next = writeOnboardingStateToStorage({
    ...readOnboardingStateFromStorage(),
    firstRunCompleted: false,
  });
  syncOnboardingState(next);
  return next;
}
