import { useEffect, useRef } from 'react';

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
