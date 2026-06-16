import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import CoreUIConfirmDialog from './CoreUIConfirmDialog';

describe('CoreUIConfirmDialog', () => {
  it('renders message as plain text without executing script', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    const malicious = '<script>alert("xss")</script>Delete model?';
    render(
      <CoreUIConfirmDialog
        open
        message={malicious}
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByText(malicious)).toBeInTheDocument();
    expect(document.querySelector('script')).toBeNull();
  });

  it('calls onConfirm when confirm is clicked', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <CoreUIConfirmDialog
        open
        message="Proceed?"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /^confirm$/i }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it('calls onCancel when cancel is clicked', () => {
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(
      <CoreUIConfirmDialog
        open
        message="Proceed?"
        onConfirm={onConfirm}
        onCancel={onCancel}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /^cancel$/i }));
    expect(onCancel).toHaveBeenCalledOnce();
  });
});
