import { useCallback, useRef, useState } from 'react';
import CoreUIConfirmDialog, { type ConfirmVariant } from './CoreUIConfirmDialog';
import { normalizeConfirmText } from './normalizeConfirmText';

export type ConfirmOptions = {
  message: string;
  title?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  variant?: ConfirmVariant;
};

type PendingConfirm = ConfirmOptions & { open: true };

export function useConfirmDialog() {
  const resolveRef = useRef<((value: boolean) => void) | null>(null);
  const [pending, setPending] = useState<PendingConfirm | null>(null);

  const confirm = useCallback((options: ConfirmOptions): Promise<boolean> => {
    const message = normalizeConfirmText(options.message);
    if (!message) return Promise.resolve(true);
    return new Promise((resolve) => {
      resolveRef.current = resolve;
      setPending({ ...options, message, open: true });
    });
  }, []);

  const settle = useCallback((accepted: boolean) => {
    resolveRef.current?.(accepted);
    resolveRef.current = null;
    setPending(null);
  }, []);

  const ConfirmDialogHost = useCallback(() => {
    if (!pending) return null;
    return (
      <CoreUIConfirmDialog
        open
        message={pending.message}
        title={pending.title}
        confirmLabel={pending.confirmLabel}
        cancelLabel={pending.cancelLabel}
        variant={pending.variant}
        onConfirm={() => settle(true)}
        onCancel={() => settle(false)}
      />
    );
  }, [pending, settle]);

  return { confirm, ConfirmDialogHost };
}
