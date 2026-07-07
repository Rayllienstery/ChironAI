import { describe, expect, it, beforeEach } from 'vitest';
import { setLocale } from '../../services/i18n.js';
import { resolveFirstRunTourSteps } from './firstRunTour.js';

describe('firstRunTour', () => {
  beforeEach(() => {
    setLocale('en');
  });

  it('starts with a language selection step', () => {
    const steps = resolveFirstRunTourSteps();
    expect(steps[0].kind).toBe('language');
    expect(steps[1].title).toBe('Welcome to ChironAI');
    expect(steps).toHaveLength(8);
    expect(steps[5].id).toBe('crawler');
  });
});
