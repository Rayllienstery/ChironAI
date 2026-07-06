import { describe, expect, it, vi } from 'vitest';
import { createBuildsTourSteps } from './contextualTours.js';

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
});
