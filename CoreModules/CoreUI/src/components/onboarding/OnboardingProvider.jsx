import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import TourEngine from './TourEngine.jsx';
import { resolveFirstRunTourSteps } from './firstRunTour.js';
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
import { setLocale } from '../../services/i18n';
import { releaseBodyScrollLock } from './tourUiLock.js';

const OnboardingContext = createContext(null);

const FIRST_RUN_KEY = '__first_run__';
const DEFAULT_TOUR_LOCALE = 'en';
const CONTEXTUAL_TOUR_COOLDOWN_MS = 1500;

function mergeRemoteOnboardingState(localState, remoteState) {
  if (!remoteState) return localState;
  if (localState.firstRunCompleted && !remoteState.firstRunCompleted) {
    return localState;
  }
  return {
    ...remoteState,
    tours: {
      ...remoteState.tours,
      ...localState.tours,
    },
  };
}

/**
 * @typedef {Object} OnboardingApi
 * @property {(tourKey: string, steps: Array, options?: { ready?: boolean }) => boolean} maybeStartContextualTour
 * @property {boolean} isTourActive
 */

export function OnboardingProvider({ children, onNavigate, onLocaleChange }) {
  const [tour, setTour] = useState({
    open: false,
    steps: [],
    stepIndex: 0,
    tourKey: '',
  });
  const [tourLocale, setTourLocale] = useState(DEFAULT_TOUR_LOCALE);
  const contextualTourCooldownRef = useRef(false);
  const contextualTourCooldownTimerRef = useRef(null);
  const tourRef = useRef(tour);

  useEffect(() => {
    tourRef.current = tour;
  }, [tour]);

  const applyTourLocale = useCallback(
    (nextLocale) => {
      const normalized = nextLocale === 'uk' ? 'uk' : DEFAULT_TOUR_LOCALE;
      setTourLocale(normalized);
      setLocale(normalized);
      onLocaleChange?.(normalized);
      setTour((current) => {
        if (!current.open || current.tourKey !== FIRST_RUN_KEY) {
          return current;
        }
        return { ...current, steps: resolveFirstRunTourSteps() };
      });
    },
    [onLocaleChange],
  );

  const openFirstRunTour = useCallback(() => {
    applyTourLocale(DEFAULT_TOUR_LOCALE);
    setTour({
      open: true,
      steps: resolveFirstRunTourSteps(),
      stepIndex: 0,
      tourKey: FIRST_RUN_KEY,
    });
  }, [applyTourLocale]);

  useEffect(() => {
    let cancelled = false;

    (async () => {
      let state = readOnboardingStateFromStorage();
      try {
        const remote = await getSettings();
        const fromSettings = parseOnboardingStateFromSettings(remote);
        if (fromSettings) {
          state = writeOnboardingStateToStorage(
            mergeRemoteOnboardingState(readOnboardingStateFromStorage(), fromSettings),
          );
        }
      } catch {
        /* server not ready */
      }
      const latest = readOnboardingStateFromStorage();
      if (!cancelled && !latest.firstRunCompleted) {
        openFirstRunTour();
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [openFirstRunTour]);

  const closeTour = useCallback(() => {
    releaseBodyScrollLock();
    setTour({ open: false, steps: [], stepIndex: 0, tourKey: '' });
  }, []);

  const startContextualTourCooldown = useCallback(() => {
    contextualTourCooldownRef.current = true;
    if (contextualTourCooldownTimerRef.current) {
      window.clearTimeout(contextualTourCooldownTimerRef.current);
    }
    contextualTourCooldownTimerRef.current = window.setTimeout(() => {
      contextualTourCooldownRef.current = false;
      contextualTourCooldownTimerRef.current = null;
    }, CONTEXTUAL_TOUR_COOLDOWN_MS);
  }, []);

  const completeTour = useCallback((tourKey) => {
    try {
      if (tourKey === FIRST_RUN_KEY) {
        markFirstRunCompleted();
        startContextualTourCooldown();
      } else if (tourKey) {
        markTourCompleted(tourKey);
      }
    } finally {
      closeTour();
    }
  }, [closeTour, startContextualTourCooldown]);

  const maybeStartContextualTour = useCallback((tourKey, steps, options = {}) => {
    const { ready = true } = options;
    if (
      !ready
      || tour.open
      || contextualTourCooldownRef.current
      || !tourKey
      || !Array.isArray(steps)
      || steps.length === 0
    ) {
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
    completeTour(tourRef.current.tourKey);
  }, [completeTour]);

  const handleFinish = useCallback(() => {
    completeTour(tourRef.current.tourKey);
  }, [completeTour]);

  useEffect(() => () => {
    if (contextualTourCooldownTimerRef.current) {
      window.clearTimeout(contextualTourCooldownTimerRef.current);
    }
  }, []);

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
        localeValue={tourLocale}
        onLocaleChange={applyTourLocale}
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
  setLocale(DEFAULT_TOUR_LOCALE);
  window.location.reload();
}
