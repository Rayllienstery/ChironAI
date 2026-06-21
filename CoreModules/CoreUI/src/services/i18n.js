/**
 * CoreUI i18n adapter (Phase 6) — reads shared JSON catalog from Localization module.
 * Production builds may bundle catalogs; dev can fetch from /api/webui/i18n/:locale later.
 */

import enCommon from '../../../Localization/localization/catalog/en/common.json';
import enXaCommon from '../../../Localization/localization/catalog/en-XA/common.json';
import ruCommon from '../../../Localization/localization/catalog/ru/common.json';

const DEFAULT_LOCALE = 'en';
const LOCALE_STORAGE_KEY = 'chironai_locale';
const catalogs = {
  en: enCommon,
  'en-XA': enXaCommon,
  ru: ruCommon,
};
export const SUPPORTED_LOCALES = [
  { id: 'en', label: 'English' },
  { id: 'ru', label: 'Русский' },
  { id: 'en-XA', label: 'Pseudo English' },
];

function storedLocale() {
  try {
    return localStorage.getItem(LOCALE_STORAGE_KEY) || DEFAULT_LOCALE;
  } catch {
    return DEFAULT_LOCALE;
  }
}

let activeLocale = storedLocale() in catalogs ? storedLocale() : DEFAULT_LOCALE;

export function setLocale(locale) {
  activeLocale = locale in catalogs ? locale : DEFAULT_LOCALE;
  try {
    localStorage.setItem(LOCALE_STORAGE_KEY, activeLocale);
  } catch {
    // safe: localStorage may be unavailable
  }
}

export function getLocale() {
  return activeLocale;
}

/**
 * @param {string} messageId
 * @param {Record<string, string | number>} [params]
 */
export function t(messageId, params = {}) {
  const catalog = catalogs[activeLocale] || catalogs[DEFAULT_LOCALE];
  const template = catalog?.[messageId] ?? messageId;
  if (!params || Object.keys(params).length === 0) return template;
  return Object.entries(params).reduce(
    (text, [key, value]) => text.replaceAll(`{${key}}`, String(value)),
    template,
  );
}
