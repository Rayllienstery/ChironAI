import { useEffect, useRef } from 'react';

/**
 * A reusable modal dialog component.
 * 
 * @param {Object} props
 * @param {string} props.title - The title displayed in the modal header.
 * @param {Function} props.onClose - Callback function invoked when the modal is closed.
 * @param {React.ReactNode} props.children - The content to be rendered inside the modal body.
 * @param {React.ReactNode} [props.footer] - Optional content to be rendered in the modal footer.
 * @param {string} [props.className] - Additional CSS classes for the modal container.
 */
export default function CoreUIModal({ title, onClose, children, footer, className = '' }) {
  const panelRef = useRef(null);

  useEffect(() => {
    const prev = document.activeElement;
    const t = setTimeout(() => {
      try {
        panelRef.current?.querySelector?.('input,select,button,textarea,[tabindex]')?.focus?.();
      } catch {
        /* ignore */
      }
    }, 0);
    return () => {
      clearTimeout(t);
      try {
        prev?.focus?.();
      } catch {
        /* ignore */
      }
    };
  }, []);

  useEffect(() => {
    const onKeyDown = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  return (
    <div
      className="coreui-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-label={title}
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose?.();
      }}
    >
      <div className={`coreui-modal${className ? ` ${className}` : ''}`} ref={panelRef}>
        <div className="coreui-modal-header">
          <h3>{title}</h3>
          <button type="button" className="coreui-modal-close-btn" onClick={onClose} aria-label="Close dialog">
            <span className="material-symbols-outlined" aria-hidden="true">close</span>
          </button>
        </div>
        <div className="coreui-modal-body">{children}</div>
        {footer ? <div className="coreui-modal-footer">{footer}</div> : null}
      </div>
    </div>
  );
}
