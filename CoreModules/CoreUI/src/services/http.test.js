import { describe, expect, it } from 'vitest';
import { extractApiError, API_BASE } from './http.js';

describe('http helpers', () => {
  it('extractApiError reads structured error message', () => {
    expect(extractApiError({ error: { code: 'x', message: 'Bad request' } })).toBe('Bad request');
  });

  it('extractApiError reads legacy string error', () => {
    expect(extractApiError({ error: 'legacy' })).toBe('legacy');
  });

  it('extractApiError uses fallback when missing', () => {
    expect(extractApiError({}, 'fallback')).toBe('fallback');
  });

  it('API_BASE matches backend contract', () => {
    expect(API_BASE).toBe('/api/webui');
  });
});
