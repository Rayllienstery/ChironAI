import CoreUIButton from './CoreUIButton';
import { formatUserError } from '../utils/userError.js';
import { t } from '../services/i18n.js';
import '../styles/components/ActionableError.css';

/**
 * User-facing error banner with optional retry and collapsible developer detail.
 *
 * @param {Object} props
 * @param {unknown} props.error - Raw error value or message string.
 * @param {() => void} [props.onRetry] - Retry handler (e.g. reload data).
 * @param {string} [props.title] - Override catalog title.
 * @param {string} [props.className] - Additional CSS classes.
 */
export default function ActionableError({ error, onRetry, title: titleOverride, className = '' }) {
  if (!error) return null;
  const raw = typeof error === 'string' ? error : error;
  const formatted = formatUserError(
    typeof raw === 'string' ? { message: raw } : raw,
  );
  const title = titleOverride || formatted.title;
  const { message, detail } = formatted;
  const showDetail =
    detail &&
    detail !== title &&
    detail !== message &&
    !message.includes(detail);

  return (
    <div
      className={['coreui-actionable-error', className].filter(Boolean).join(' ')}
      role="alert"
    >
      <div className="coreui-actionable-error__body">
        <span className="material-symbols-outlined coreui-actionable-error__icon" aria-hidden="true">
          error_outline
        </span>
        <div className="coreui-actionable-error__text">
          <strong className="coreui-actionable-error__title">{title}</strong>
          <p className="coreui-actionable-error__message">{message}</p>
          {showDetail ? (
            <details className="coreui-actionable-error__details">
              <summary>{t('common.error.details')}</summary>
              <pre>{detail}</pre>
            </details>
          ) : null}
        </div>
      </div>
      {typeof onRetry === 'function' ? (
        <CoreUIButton variant="primary" size="sm" type="button" onClick={onRetry}>
          {t('common.error.retry')}
        </CoreUIButton>
      ) : null}
    </div>
  );
}
