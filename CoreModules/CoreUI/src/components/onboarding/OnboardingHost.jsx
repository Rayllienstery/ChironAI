import { useCallback, useEffect, useState } from 'react';
import TourEngine from './TourEngine.jsx';
import { FIRST_RUN_TOUR_STEPS } from './firstRunTour.js';
import {
  ONBOARDING_SETTINGS_KEY,
  parseOnboardingStateFromSettings,
  readOnboardingStateFromStorage,
  serializeOnboardingStateForSettings,
  writeOnboardingStateToStorage,
} from './onboardingState.js';
import { getSettings, updateSettings } from '../../services/api.js';

/**
 * Hosts the first-run tour and persists completion state.
 *
 * @param {Object} props
 * @param {(tabId: string) => void} [props.onNavigate] - Optional tab switch for highlighted steps.
 */
export default function OnboardingHost({ onNavigate }) {
  const [open, setOpen] = useState(false);
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      let state = readOnboardingStateFromStorage();
      try {
        const remote = await getSettings();
        const fromSettings = parseOnboardingStateFromSettings(remote);
        if (fromSettings) {
          state = writeOnboardingStateToStorage(fromSettings);
        }
      } catch {
        /* offline / server not ready */
      }
      if (!cancelled && !state.firstRunCompleted) {
        setOpen(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const persistCompletion = useCallback(() => {
    const next = writeOnboardingStateToStorage({
      ...readOnboardingStateFromStorage(),
      firstRunCompleted: true,
    });
    void updateSettings({
      [ONBOARDING_SETTINGS_KEY]: serializeOnboardingStateForSettings(next),
    }).catch(() => {
      /* localStorage is the fallback */
    });
  }, []);

  const closeTour = useCallback(() => {
    setOpen(false);
    setStepIndex(0);
  }, []);

  const handleSkip = useCallback(() => {
    persistCompletion();
    closeTour();
  }, [closeTour, persistCompletion]);

  const handleFinish = useCallback(() => {
    persistCompletion();
    closeTour();
  }, [closeTour, persistCompletion]);

  const handleNext = useCallback(() => {
    setStepIndex((index) => {
      const nextIndex = Math.min(index + 1, FIRST_RUN_TOUR_STEPS.length - 1);
      const nextStep = FIRST_RUN_TOUR_STEPS[nextIndex];
      if (nextStep?.target) {
        const tabId = nextStep.target.match(/data-tour="([^"]+)"/)?.[1];
        if (tabId && tabId !== 'settings') onNavigate?.(tabId);
      }
      return nextIndex;
    });
  }, [onNavigate]);

  const handleBack = useCallback(() => {
    setStepIndex((index) => Math.max(0, index - 1));
  }, []);

  return (
    <TourEngine
      open={open}
      steps={FIRST_RUN_TOUR_STEPS}
      stepIndex={stepIndex}
      onBack={handleBack}
      onNext={handleNext}
      onSkip={handleSkip}
      onFinish={handleFinish}
    />
  );
}

/** Restart the first-run tour (Settings action). */
export function restartFirstRunTour() {
  const next = writeOnboardingStateToStorage({
    ...readOnboardingStateFromStorage(),
    firstRunCompleted: false,
  });
  void updateSettings({
    [ONBOARDING_SETTINGS_KEY]: serializeOnboardingStateForSettings(next),
  }).catch(() => {});
  window.location.reload();
}
