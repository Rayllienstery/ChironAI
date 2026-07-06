import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import TourEngine from './TourEngine.jsx';
import { setLocale } from '../../services/i18n.js';

describe('TourEngine', () => {
  beforeEach(() => {
    setLocale('en');
  });

  const steps = [
    { id: 'welcome', title: 'Welcome', body: 'Intro copy.' },
    { id: 'dashboard', title: 'Dashboard', body: 'Health overview.', target: '[data-tour="dashboard"]' },
  ];

  it('renders the active step and advances', () => {
    const onNext = vi.fn();
    render(
      <TourEngine
        open
        steps={steps}
        stepIndex={0}
        onNext={onNext}
        onBack={vi.fn()}
        onSkip={vi.fn()}
        onFinish={vi.fn()}
      />,
    );

    expect(screen.getByRole('dialog', { name: 'Welcome' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Next' }));
    expect(onNext).toHaveBeenCalled();
  });

  it('calls onSkip from the skip action', () => {
    const onSkip = vi.fn();
    render(
      <TourEngine
        open
        steps={steps}
        stepIndex={0}
        onNext={vi.fn()}
        onBack={vi.fn()}
        onSkip={onSkip}
        onFinish={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Skip tour' }));
    expect(onSkip).toHaveBeenCalled();
  });

  it('releases body scroll lock when the tour closes', () => {
    document.body.style.overflow = '';
    const { rerender } = render(
      <TourEngine
        open
        steps={steps}
        stepIndex={0}
        onNext={vi.fn()}
        onBack={vi.fn()}
        onSkip={vi.fn()}
        onFinish={vi.fn()}
      />,
    );

    expect(document.body.style.overflow).toBe('hidden');
    rerender(
      <TourEngine
        open={false}
        steps={steps}
        stepIndex={0}
        onNext={vi.fn()}
        onBack={vi.fn()}
        onSkip={vi.fn()}
        onFinish={vi.fn()}
      />,
    );
    expect(document.body.style.overflow).toBe('');
  });

  it('renders language picker on the language step', () => {
    render(
      <TourEngine
        open
        steps={[
          { id: 'language', kind: 'language', title: 'Choose your language', body: 'Pick a language.' },
        ]}
        stepIndex={0}
        localeValue="en"
        onLocaleChange={vi.fn()}
        onNext={vi.fn()}
        onBack={vi.fn()}
        onSkip={vi.fn()}
        onFinish={vi.fn()}
      />,
    );

    expect(screen.getByRole('radio', { name: 'English' })).toBeChecked();
    expect(screen.getByRole('radio', { name: /українська/i })).toBeInTheDocument();
  });
});
