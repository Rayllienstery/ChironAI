import { describe, expect, it, beforeEach } from 'vitest';
import { getLocale, setLocale } from './i18n.js';

describe('i18n locale API', () => {
  beforeEach(() => {
    setLocale('en');
  });

  it('getLocale returns the active locale', () => {
    expect(getLocale()).toBe('en');
    setLocale('en-XA');
    expect(getLocale()).toBe('en-XA');
  });

  it('setLocale falls back to en for unknown locales', () => {
    setLocale('fr');
    expect(getLocale()).toBe('en');
  });
});
