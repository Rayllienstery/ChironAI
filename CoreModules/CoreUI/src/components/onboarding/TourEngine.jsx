import { useEffect, useLayoutEffect, useState } from 'react';
import CoreUIButton from '../CoreUIButton';
import '../../styles/components/TourEngine.css';

function measureTarget(selector) {
  if (!selector || typeof document === 'undefined') return null;
  const element = document.querySelector(selector);
  if (!element) return null;
  const rect = element.getBoundingClientRect();
  return {
    top: rect.top,
    left: rect.left,
    width: rect.width,
    height: rect.height,
  };
}

/**
 * Lightweight spotlight tour engine with M3 tooltip card.
 */
export default function TourEngine({
  open,
  steps = [],
  stepIndex = 0,
  onBack,
  onNext,
  onSkip,
  onFinish,
}) {
  const step = steps[stepIndex] || null;
  const [spotlight, setSpotlight] = useState(null);

  useLayoutEffect(() => {
    if (!open || !step) {
      setSpotlight(null);
      return undefined;
    }

    const update = () => setSpotlight(measureTarget(step.target));
    update();

    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [open, step, stepIndex]);

  useEffect(() => {
    if (!open) return undefined;
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  if (!open || !step) return null;

  const isLast = stepIndex >= steps.length - 1;
  const isFirst = stepIndex === 0;
  const tooltipStyle = spotlight
    ? {
        top: Math.min(window.innerHeight - 16, spotlight.top + spotlight.height + 12),
        left: Math.min(window.innerWidth - 16, Math.max(16, spotlight.left)),
      }
    : {
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
      };

  return (
    <div className="tour-engine" role="presentation">
      <div className="tour-engine__scrim" aria-hidden="true" />
      {spotlight ? (
        <div
          className="tour-engine__spotlight"
          style={{
            top: spotlight.top - 4,
            left: spotlight.left - 4,
            width: spotlight.width + 8,
            height: spotlight.height + 8,
          }}
          aria-hidden="true"
        />
      ) : null}
      <div
        className={`tour-engine__card${spotlight ? '' : ' tour-engine__card--centered'}`}
        style={tooltipStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-engine-title"
        aria-describedby="tour-engine-body"
      >
        <p className="tour-engine__progress" aria-live="polite">
          Step {stepIndex + 1} of {steps.length}
        </p>
        <h2 id="tour-engine-title" className="tour-engine__title">
          {step.title}
        </h2>
        <p id="tour-engine-body" className="tour-engine__body">
          {step.body}
        </p>
        <div className="tour-engine__actions">
          <CoreUIButton type="button" variant="ghost" onClick={onSkip}>
            Skip tour
          </CoreUIButton>
          <div className="tour-engine__actions-main">
            {!isFirst ? (
              <CoreUIButton type="button" variant="default" onClick={onBack}>
                Back
              </CoreUIButton>
            ) : null}
            <CoreUIButton
              type="button"
              variant="primary"
              onClick={isLast ? onFinish : onNext}
            >
              {isLast ? 'Finish' : 'Next'}
            </CoreUIButton>
          </div>
        </div>
      </div>
    </div>
  );
}
