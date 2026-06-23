import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CoreUISubtabs from './CoreUISubtabs.jsx';

describe('CoreUISubtabs', () => {
  it('renders compact tab semantics and calls onChange with the selected tab', () => {
    const onChange = vi.fn();
    const tabs = [
      { id: 'logs', label: 'Logs' },
      { id: 'metrics', label: 'Metrics' },
    ];

    render(
      <CoreUISubtabs
        tabs={tabs}
        value="logs"
        onChange={onChange}
        ariaLabel="Panel sections"
      />,
    );

    expect(screen.getByRole('tablist', { name: 'Panel sections' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Logs' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Metrics' })).toHaveAttribute('aria-selected', 'false');

    fireEvent.click(screen.getByRole('tab', { name: 'Metrics' }));

    expect(onChange).toHaveBeenCalledWith('metrics', tabs[1]);
  });
});
