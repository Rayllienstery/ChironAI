import CoreUIButton from '../CoreUIButton';
import { useHelpPanel } from '../help/HelpPanelContext.jsx';

/**
 * Compact info icon that opens contextual help in the Help panel drawer.
 *
 * @param {Object} props
 * @param {string} props.helpRef - Help article slug or `slug#anchor`.
 * @param {string} [props.label] - Accessible label for the field being explained.
 * @param {string} [props.className]
 */
export default function InfoButton({ helpRef, label = '', className = '' }) {
  const { openHelp } = useHelpPanel();
  const ariaLabel = label ? `Help: ${label}` : 'Open field help';

  return (
    <CoreUIButton
      type="button"
      variant="icon"
      size="icon"
      className={`info-button${className ? ` ${className}` : ''}`}
      aria-label={ariaLabel}
      onClick={() => openHelp(helpRef, label)}
    >
      <span className="material-symbols-outlined info-button__icon" aria-hidden="true">
        info
      </span>
    </CoreUIButton>
  );
}

/**
 * Label row for form fields with an optional contextual help button.
 */
export function FieldLabelWithHelp({ children, helpRef, helpLabel }) {
  const labelText = helpLabel || (typeof children === 'string' ? children : '');
  return (
    <span className="coreui-form-field-label-row">
      <span>{children}</span>
      {helpRef ? <InfoButton helpRef={helpRef} label={labelText} /> : null}
    </span>
  );
}
