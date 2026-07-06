/**
 * CoreUI i18n adapter (Phase 6) — reads shared JSON catalog from Localization module.
 * Production builds may bundle catalogs; dev can fetch from /api/webui/i18n/:locale later.
 */

import enCommon from '../../../Localization/localization/catalog/en/common.json';
import ukCommon from '../../../Localization/localization/catalog/uk/common.json';

const DEFAULT_LOCALE = 'en';
const LOCALE_STORAGE_KEY = 'chironai_locale';
const catalogs = {
  en: enCommon,
  uk: ukCommon,
};
export const SUPPORTED_LOCALES = [
  { id: 'en', label: 'English' },
  { id: 'uk', label: 'Українська' },
];

function normalizeLocale(locale) {
  const value = String(locale || '').trim();
  if (value === 'ru' || value === 'en-XA') return value === 'ru' ? 'uk' : 'en';
  return value;
}

function storedLocale() {
  try {
    return normalizeLocale(localStorage.getItem(LOCALE_STORAGE_KEY) || DEFAULT_LOCALE);
  } catch {
    return DEFAULT_LOCALE;
  }
}

let activeLocale = storedLocale() in catalogs ? storedLocale() : DEFAULT_LOCALE;

export function setLocale(locale) {
  const normalized = normalizeLocale(locale);
  activeLocale = normalized in catalogs ? normalized : DEFAULT_LOCALE;
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
