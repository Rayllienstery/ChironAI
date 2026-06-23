import { describe, expect, it } from 'vitest';
import { formatElapsedMs, parseTimeMs } from './elapsedTime.js';

describe('elapsedTime', () => {
  describe('formatElapsedMs', () => {
    it('formats sub-hour durations as m:ss', () => {
      expect(formatElapsedMs(65_000)).toBe('1:05');
      expect(formatElapsedMs(0)).toBe('0:00');
    });

    it('formats hour-plus durations as h:mm:ss', () => {
      expect(formatElapsedMs(3_661_000)).toBe('1:01:01');
    });

    it('clamps negative values to zero', () => {
      expect(formatElapsedMs(-500)).toBe('0:00');
    });
  });

  describe('parseTimeMs', () => {
    it('accepts finite numbers', () => {
      expect(parseTimeMs(42)).toBe(42);
    });

    it('parses ISO date strings', () => {
      const parsed = parseTimeMs('2026-06-16T12:00:00.000Z');
      expect(parsed).toBe(Date.parse('2026-06-16T12:00:00.000Z'));
    });

    it('returns null for invalid input', () => {
      expect(parseTimeMs('not-a-date')).toBeNull();
      expect(parseTimeMs(undefined)).toBeNull();
    });
  });
});
