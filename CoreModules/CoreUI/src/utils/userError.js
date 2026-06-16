import { t } from '../services/i18n.js';

/**
 * Detect fetch/network failures that should show a connectivity hint.
 * @param {unknown} error
 */
export function isNetworkLikeError(error) {
  const msg = String(error?.message || error || '').toLowerCase();
  return (
    msg.includes('failed to fetch') ||
    msg.includes('networkerror') ||
    msg.includes('load failed') ||
    msg.includes('network error') ||
    msg.includes('typeerror: failed to fetch') ||
    msg.includes('request timed out')
  );
}

/**
 * Map a thrown value or message to user-facing copy (catalog) plus optional developer detail.
 * @param {unknown} error
 * @returns {{ title: string, message: string, detail: string | null, isNetwork: boolean }}
 */
export function formatUserError(error) {
  const detail = String(error?.message || error || '').trim() || null;
  const isNetwork = isNetworkLikeError(error);
  if (isNetwork) {
    return {
      title: t('common.error.network'),
      message: t('common.error.network_hint'),
      detail,
      isNetwork: true,
    };
  }
  return {
    title: t('common.error.generic'),
    message: t('common.error.generic_hint'),
    detail,
    isNetwork: false,
  };
}
