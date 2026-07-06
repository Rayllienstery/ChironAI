import { describe, expect, it, vi, beforeEach } from 'vitest';
import { setLocale } from '../../services/i18n.js';
import {
  CRAWLER_TOUR_STEPS,
  EXTENSIONS_TOUR_STEPS,
  PROMPTS_TOUR_STEPS,
  PROVIDERS_TOUR_STEPS,
  createBuildsTourSteps,
  resolveCrawlerTourSteps,
} from './contextualTours.js';

describe('contextualTours', () => {
  beforeEach(() => {
    setLocale('en');
  });

  it('builds tour wires wizard step callbacks', () => {
    const goToBasicStep = vi.fn();
    const goToRagStep = vi.fn();
    const steps = createBuildsTourSteps({ goToBasicStep, goToRagStep });

    steps[3].onEnter?.();
    expect(goToRagStep).toHaveBeenCalled();

    steps[1].onEnter?.();
    expect(goToBasicStep).toHaveBeenCalled();
  });

  it('defines stable step metadata for other feature tours', () => {
    expect(EXTENSIONS_TOUR_STEPS).toHaveLength(2);
    expect(PROMPTS_TOUR_STEPS).toHaveLength(2);
    expect(PROVIDERS_TOUR_STEPS).toHaveLength(3);
    expect(CRAWLER_TOUR_STEPS).toHaveLength(2);
    expect(EXTENSIONS_TOUR_STEPS[0].target).toBe('[data-tour="extensions-header"]');
    expect(PROVIDERS_TOUR_STEPS[1].target).toBe('[data-tour="providers-custom-list"]');
    expect(PROMPTS_TOUR_STEPS[1].target).toBe('[data-tour="template-editor-panel"]');
    expect(CRAWLER_TOUR_STEPS[1].target).toBe('[data-tour="crawler-sources"]');
  });

  it('resolves localized titles for the active locale', () => {
    setLocale('uk');
    expect(resolveCrawlerTourSteps()[0].title).toBe('Краулер / Індексатор');
  });
});
