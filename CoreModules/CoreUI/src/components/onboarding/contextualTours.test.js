import { describe, expect, it, vi } from 'vitest';
import {
  CRAWLER_TOUR_STEPS,
  EXTENSIONS_TOUR_STEPS,
  PROMPTS_TOUR_STEPS,
  createBuildsTourSteps,
} from './contextualTours.js';

describe('contextualTours', () => {
  it('builds tour wires wizard step callbacks', () => {
    const goToBasicStep = vi.fn();
    const goToRagStep = vi.fn();
    const steps = createBuildsTourSteps({ goToBasicStep, goToRagStep });

    steps[2].onEnter?.();
    expect(goToRagStep).toHaveBeenCalled();

    steps[1].onEnter?.();
    expect(goToBasicStep).toHaveBeenCalled();
  });

  it('defines stable step metadata for other feature tours', () => {
    expect(EXTENSIONS_TOUR_STEPS).toHaveLength(2);
    expect(PROMPTS_TOUR_STEPS).toHaveLength(2);
    expect(CRAWLER_TOUR_STEPS).toHaveLength(2);
    expect(EXTENSIONS_TOUR_STEPS[0].target).toBe('[data-tour="extensions-header"]');
    expect(PROMPTS_TOUR_STEPS[1].target).toBe('[data-tour="template-editor-panel"]');
    expect(CRAWLER_TOUR_STEPS[1].target).toBe('[data-tour="crawler-sources"]');
  });
});
