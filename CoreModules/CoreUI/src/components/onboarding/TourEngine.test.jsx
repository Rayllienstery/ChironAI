import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import TourEngine from './TourEngine.jsx';

describe('TourEngine', () => {
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
});
