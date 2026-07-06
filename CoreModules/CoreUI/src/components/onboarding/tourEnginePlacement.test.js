import { describe, expect, it } from 'vitest';
import { computeTourCardStyle } from './tourEnginePlacement.js';

describe('tourEnginePlacement', () => {
  it('places sidebar targets to the right of the nav item', () => {
    const style = computeTourCardStyle({
      top: 400,
      left: 12,
      width: 236,
      height: 40,
      borderRadius: '12px',
      placement: 'sidebar',
    });

    expect(style.left).toBe(12 + 236 + 12);
    expect(style.transform).toBe('translateY(-50%)');
  });

  it('centers welcome steps without a target', () => {
    expect(computeTourCardStyle(null)).toEqual({
      top: '50%',
      left: '50%',
      transform: 'translate(-50%, -50%)',
    });
  });
});
