import CoreUIButton from './CoreUIButton';
import CoreUIModal from './CoreUIModal';
import { normalizeConfirmText } from './normalizeConfirmText';

export type ConfirmVariant = 'default' | 'danger';

export type CoreUIConfirmDialogProps = {
  open: boolean;
  message: string;
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: ConfirmVariant;
  onConfirm: () => void;
  onCancel: () => void;
};

export default function CoreUIConfirmDialog({
  open,
  message,
  title = 'Confirm',
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  variant = 'default',
  onConfirm,
  onCancel,
}: CoreUIConfirmDialogProps) {
  if (!open) return null;

  const safeMessage = normalizeConfirmText(message);

  return (
    <CoreUIModal
      title={title}
      onClose={onCancel}
      className="coreui-confirm-dialog"
      footer={(
        <div className="coreui-confirm-dialog__actions">
          <CoreUIButton variant="ghost" onClick={onCancel}>
            {cancelLabel}
          </CoreUIButton>
          <CoreUIButton
            variant={variant === 'danger' ? 'danger' : 'primary'}
            onClick={onConfirm}
          >
            {confirmLabel}
          </CoreUIButton>
        </div>
      )}
    >
      <p className="coreui-confirm-dialog__message">{safeMessage}</p>
    </CoreUIModal>
  );
}
