import { useEffect, useMemo, useRef } from 'react';
import { useOnboarding } from './OnboardingProvider.jsx';

/**
 * Start a contextual tour once when `enabled` becomes true.
 */
export function useContextualTour(tourKey, steps, enabled = true) {
  const { maybeStartContextualTour, isTourActive } = useOnboarding();
  const startedRef = useRef(false);
  const stableSteps = useMemo(() => steps, [steps]);

  useEffect(() => {
    startedRef.current = false;
  }, [tourKey, enabled]);

  useEffect(() => {
    if (!enabled || isTourActive || startedRef.current) return undefined;
    const timer = window.setTimeout(() => {
      const started = maybeStartContextualTour(tourKey, stableSteps, { ready: true });
      if (started) startedRef.current = true;
    }, 450);
    return () => window.clearTimeout(timer);
  }, [enabled, isTourActive, maybeStartContextualTour, stableSteps, tourKey]);
}
