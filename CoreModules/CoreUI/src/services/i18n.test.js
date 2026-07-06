import { describe, expect, it, beforeEach } from 'vitest';
import { getLocale, setLocale, t } from './i18n.js';
import enCommon from '../../../Localization/localization/catalog/en/common.json';
import ukCommon from '../../../Localization/localization/catalog/uk/common.json';

describe('i18n locale API', () => {
  beforeEach(() => {
    setLocale('en');
  });

  it('getLocale returns the active locale', () => {
    expect(getLocale()).toBe('en');
    setLocale('uk');
    expect(getLocale()).toBe('uk');
  });

  it('migrates removed pseudo and legacy locale codes', () => {
    setLocale('en-XA');
    expect(getLocale()).toBe('en');
    setLocale('ru');
    expect(getLocale()).toBe('uk');
  });

  it('setLocale falls back to en for unknown locales', () => {
    setLocale('fr');
    expect(getLocale()).toBe('en');
  });

  it('resolves catalog strings for error and empty states', () => {
    expect(t('common.error.retry')).toBe('Try again');
    expect(t('crawler.empty_sources')).toMatch(/crawl sources/i);
  });

  it('uk catalog resolves translated strings and shares message ids', () => {
    setLocale('uk');
    expect(t('nav.settings')).toBe('Налаштування');
    expect(Object.keys(ukCommon).sort()).toEqual(Object.keys(enCommon).sort());
  });
});
