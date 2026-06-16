import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import ActionableError from './ActionableError.jsx';
import { setLocale } from '../services/i18n.js';

describe('ActionableError', () => {
  beforeEach(() => {
    setLocale('en');
  });

  it('renders actionable copy and retry button', () => {
    const onRetry = vi.fn();
    render(<ActionableError error={new Error('Failed to fetch')} onRetry={onRetry} />);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.getByText(/network error/i)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /try again/i }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it('hides technical details behind summary', () => {
    render(<ActionableError error={new Error('disk full')} />);
    expect(screen.getByText(/technical details/i)).toBeInTheDocument();
    expect(screen.queryByText('disk full')).not.toBeVisible();
  });
});
