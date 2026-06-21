import { describe, expect, it, beforeEach } from 'vitest';
import { getLocale, setLocale, t } from './i18n.js';
import enCommon from '../../../Localization/localization/catalog/en/common.json';
import enXaCommon from '../../../Localization/localization/catalog/en-XA/common.json';
import ruCommon from '../../../Localization/localization/catalog/ru/common.json';

describe('i18n locale API', () => {
  beforeEach(() => {
    setLocale('en');
  });

  it('getLocale returns the active locale', () => {
    expect(getLocale()).toBe('en');
    setLocale('en-XA');
    expect(getLocale()).toBe('en-XA');
    setLocale('ru');
    expect(getLocale()).toBe('ru');
  });

  it('setLocale falls back to en for unknown locales', () => {
    setLocale('fr');
    expect(getLocale()).toBe('en');
  });

  it('resolves catalog strings for error and empty states', () => {
    expect(t('common.error.retry')).toBe('Try again');
    expect(t('crawler.empty_sources')).toMatch(/crawl sources/i);
  });

  it('en and en-XA catalogs share message ids', () => {
    expect(Object.keys(enXaCommon).sort()).toEqual(Object.keys(enCommon).sort());
  });

  it('ru catalog resolves translated strings and shares message ids', () => {
    setLocale('ru');
    expect(t('nav.settings')).toBe('Настройки');
    expect(Object.keys(ruCommon).sort()).toEqual(Object.keys(enCommon).sort());
  });
});
