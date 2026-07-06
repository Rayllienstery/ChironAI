import { useLayoutEffect, useState } from 'react';
import CoreUIButton from '../CoreUIButton';
import { SUPPORTED_LOCALES, t } from '../../services/i18n';
import { releaseBodyScrollLock } from './tourUiLock.js';
import { computeTourCardStyle, measureTourTarget } from './tourEnginePlacement.js';
import '../../styles/components/TourEngine.css';

function TourLanguagePicker({ value, onChange }) {
  return (
    <div
      className="tour-engine__locale-picker"
      role="radiogroup"
      aria-label={t('onboarding.language.title')}
    >
      {SUPPORTED_LOCALES.map((item) => (
        <label
          key={item.id}
          className={`tour-engine__locale-option ${value === item.id ? 'tour-engine__locale-option--active' : ''}`}
        >
          <input
            type="radio"
            name="tour-locale"
            value={item.id}
            checked={value === item.id}
            onChange={() => onChange(item.id)}
          />
          <span>{item.label}</span>
        </label>
      ))}
    </div>
  );
}

/**
 * Lightweight spotlight tour engine aligned with CoreUI modal surfaces.
 */
export default function TourEngine({
  open,
  steps = [],
  stepIndex = 0,
  localeValue = 'en',
  onLocaleChange,
  onBack,
  onNext,
  onSkip,
  onFinish,
}) {
  const step = steps[stepIndex] || null;
  const [spotlight, setSpotlight] = useState(null);
  const [cardStyle, setCardStyle] = useState(() => computeTourCardStyle(null));
  const isOverlayVisible = Boolean(open && step);

  useLayoutEffect(() => {
    if (!isOverlayVisible || !step || step.kind === 'language') {
      setSpotlight(null);
      setCardStyle(computeTourCardStyle(null));
      return undefined;
    }

    const update = () => {
      const nextSpotlight = measureTourTarget(step.target);
      setSpotlight(nextSpotlight);
      setCardStyle(computeTourCardStyle(nextSpotlight));
    };
    update();

    window.addEventListener('resize', update);
    window.addEventListener('scroll', update, true);
    return () => {
      window.removeEventListener('resize', update);
      window.removeEventListener('scroll', update, true);
    };
  }, [isOverlayVisible, step, stepIndex]);

  useLayoutEffect(() => {
    if (!isOverlayVisible) {
      releaseBodyScrollLock();
      return undefined;
    }
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
      releaseBodyScrollLock();
    };
  }, [isOverlayVisible]);

  if (!isOverlayVisible) return null;

  const isLast = stepIndex >= steps.length - 1;
  const isFirst = stepIndex === 0;
  const isLanguageStep = step.kind === 'language';

  return (
    <div className="tour-engine" role="presentation">
      {!spotlight ? <div className="tour-engine__scrim" aria-hidden="true" /> : null}
      {spotlight ? (
        <div
          className="tour-engine__spotlight"
          style={{
            top: spotlight.top - 4,
            left: spotlight.left - 4,
            width: spotlight.width + 8,
            height: spotlight.height + 8,
            borderRadius: spotlight.borderRadius,
          }}
          aria-hidden="true"
        />
      ) : null}
      <div
        className="tour-engine__card"
        style={cardStyle}
        role="dialog"
        aria-modal="true"
        aria-labelledby="tour-engine-title"
        aria-describedby="tour-engine-body"
      >
        <header className="tour-engine__card-header">
          <p className="tour-engine__progress" aria-live="polite">
            {t('onboarding.tour.progress', { current: stepIndex + 1, total: steps.length })}
          </p>
          <h2 id="tour-engine-title" className="tour-engine__title">
            {step.title}
          </h2>
        </header>
        <p id="tour-engine-body" className="tour-engine__body">
          {step.body}
        </p>
        {isLanguageStep ? (
          <TourLanguagePicker value={localeValue} onChange={onLocaleChange} />
        ) : null}
        <footer className="tour-engine__footer">
          <CoreUIButton type="button" variant="ghost" onClick={onSkip}>
            {t('onboarding.tour.skip')}
          </CoreUIButton>
          <div className="tour-engine__footer-main">
            {!isFirst ? (
              <CoreUIButton type="button" variant="default" onClick={onBack}>
                {t('onboarding.tour.back')}
              </CoreUIButton>
            ) : null}
            <CoreUIButton
              type="button"
              variant="primary"
              onClick={isLast ? onFinish : onNext}
            >
              {isLast ? t('onboarding.tour.finish') : t('onboarding.tour.next')}
            </CoreUIButton>
          </div>
        </footer>
      </div>
    </div>
  );
}
