import { describe, expect, it, beforeEach } from 'vitest';
import { setLocale } from '../services/i18n.js';
import { formatUserError, isNetworkLikeError } from './userError.js';

describe('userError', () => {
  beforeEach(() => {
    setLocale('en');
  });

  it('detects network-like failures', () => {
    expect(isNetworkLikeError(new Error('Failed to fetch'))).toBe(true);
    expect(isNetworkLikeError(new Error('Request timed out after 5000ms'))).toBe(true);
    expect(isNetworkLikeError(new Error('Validation failed'))).toBe(false);
  });

  it('maps network errors to catalog copy', () => {
    const formatted = formatUserError(new Error('Failed to fetch'));
    expect(formatted.isNetwork).toBe(true);
    expect(formatted.title).toMatch(/network/i);
    expect(formatted.message).toMatch(/backend/i);
    expect(formatted.detail).toBe('Failed to fetch');
  });

  it('maps generic errors with developer detail', () => {
    const formatted = formatUserError(new Error('Index out of range'));
    expect(formatted.isNetwork).toBe(false);
    expect(formatted.title).toMatch(/something went wrong/i);
    expect(formatted.detail).toBe('Index out of range');
  });
});
