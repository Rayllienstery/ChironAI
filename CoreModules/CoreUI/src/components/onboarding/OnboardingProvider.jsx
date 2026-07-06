import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import TourEngine from './TourEngine.jsx';
import { FIRST_RUN_TOUR_STEPS } from './firstRunTour.js';
import {
  markFirstRunCompleted,
  markTourCompleted,
  resetFirstRunTour,
} from './onboardingPersistence.js';
import {
  parseOnboardingStateFromSettings,
  readOnboardingStateFromStorage,
  writeOnboardingStateToStorage,
} from './onboardingState.js';
import { getSettings } from '../../services/api.js';

const OnboardingContext = createContext(null);

const FIRST_RUN_KEY = '__first_run__';

/**
 * @typedef {Object} OnboardingApi
 * @property {(tourKey: string, steps: Array, options?: { ready?: boolean }) => boolean} maybeStartContextualTour
 * @property {boolean} isTourActive
 */

export function OnboardingProvider({ children, onNavigate }) {
  const [tour, setTour] = useState({
    open: false,
    steps: [],
    stepIndex: 0,
    tourKey: '',
  });

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
        /* server not ready */
      }
      if (!cancelled && !state.firstRunCompleted) {
        setTour({
          open: true,
          steps: FIRST_RUN_TOUR_STEPS,
          stepIndex: 0,
          tourKey: FIRST_RUN_KEY,
        });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const closeTour = useCallback(() => {
    setTour({ open: false, steps: [], stepIndex: 0, tourKey: '' });
  }, []);

  const completeTour = useCallback((tourKey) => {
    if (tourKey === FIRST_RUN_KEY) {
      markFirstRunCompleted();
    } else if (tourKey) {
      markTourCompleted(tourKey);
    }
    closeTour();
  }, [closeTour]);

  const maybeStartContextualTour = useCallback((tourKey, steps, options = {}) => {
    const { ready = true } = options;
    if (!ready || tour.open || !tourKey || !Array.isArray(steps) || steps.length === 0) {
      return false;
    }
    const state = readOnboardingStateFromStorage();
    if (!state.firstRunCompleted || state.tours[tourKey]) {
      return false;
    }
    setTour({
      open: true,
      steps,
      stepIndex: 0,
      tourKey,
    });
    return true;
  }, [tour.open]);

  const runStepEnter = useCallback((index, steps) => {
    const step = steps[index];
    if (!step || typeof step.onEnter !== 'function') return;
    step.onEnter();
  }, []);

  useEffect(() => {
    if (!tour.open) return;
    runStepEnter(tour.stepIndex, tour.steps);
  }, [tour.open, tour.stepIndex, tour.steps, runStepEnter]);

  const handleNext = useCallback(() => {
    setTour((current) => {
      const nextIndex = Math.min(current.stepIndex + 1, current.steps.length - 1);
      const nextStep = current.steps[nextIndex];
      if (current.tourKey === FIRST_RUN_KEY && nextStep?.target) {
        const tabId = nextStep.target.match(/data-tour="([^"]+)"/)?.[1];
        if (tabId && tabId !== 'settings') onNavigate?.(tabId);
      }
      return { ...current, stepIndex: nextIndex };
    });
  }, [onNavigate]);

  const handleBack = useCallback(() => {
    setTour((current) => ({
      ...current,
      stepIndex: Math.max(0, current.stepIndex - 1),
    }));
  }, []);

  const handleSkip = useCallback(() => {
    completeTour(tour.tourKey);
  }, [completeTour, tour.tourKey]);

  const handleFinish = useCallback(() => {
    completeTour(tour.tourKey);
  }, [completeTour, tour.tourKey]);

  const value = useMemo(
    () => ({
      maybeStartContextualTour,
      isTourActive: tour.open,
    }),
    [maybeStartContextualTour, tour.open],
  );

  return (
    <OnboardingContext.Provider value={value}>
      {children}
      <TourEngine
        open={tour.open}
        steps={tour.steps}
        stepIndex={tour.stepIndex}
        onBack={handleBack}
        onNext={handleNext}
        onSkip={handleSkip}
        onFinish={handleFinish}
      />
    </OnboardingContext.Provider>
  );
}

/** @returns {OnboardingApi} */
export function useOnboarding() {
  const ctx = useContext(OnboardingContext);
  if (!ctx) {
    throw new Error('useOnboarding must be used within OnboardingProvider');
  }
  return ctx;
}

export function restartFirstRunTour() {
  resetFirstRunTour();
  window.location.reload();
}
