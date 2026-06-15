/**
 * CoreUI i18n adapter (Phase 6) — reads shared JSON catalog from Localization module.
 * Production builds may bundle catalogs; dev can fetch from /api/webui/i18n/:locale later.
 */

import enCommon from '../../../Localization/localization/catalog/en/common.json';

const DEFAULT_LOCALE = 'en';
const catalogs = {
  en: enCommon,
};

let activeLocale = DEFAULT_LOCALE;

export function setLocale(locale) {
  activeLocale = locale in catalogs ? locale : DEFAULT_LOCALE;
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
