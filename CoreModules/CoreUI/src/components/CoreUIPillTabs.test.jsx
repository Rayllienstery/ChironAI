import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CoreUIPillTabs from './CoreUIPillTabs.jsx';

describe('CoreUIPillTabs', () => {
  it('renders accessible tabs and reports selected tab changes', () => {
    const onChange = vi.fn();
    const tabs = [
      { id: 'overview', label: 'Overview' },
      { id: 'details', label: 'Details' },
    ];

    render(
      <CoreUIPillTabs
        tabs={tabs}
        value="overview"
        onChange={onChange}
        ariaLabel="Primary sections"
      />,
    );

    expect(screen.getByRole('tablist', { name: 'Primary sections' })).toBeInTheDocument();
    expect(screen.getByRole('tab', { name: 'Overview' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tab', { name: 'Details' })).toHaveAttribute('aria-selected', 'false');

    fireEvent.click(screen.getByRole('tab', { name: 'Details' }));

    expect(onChange).toHaveBeenCalledWith('details', tabs[1]);
  });

  it('supports custom key, label, and button props', () => {
    render(
      <CoreUIPillTabs
        tabs={[{ slug: 'alpha', title: 'Alpha' }]}
        value="alpha"
        getKey={(tab) => tab.slug}
        getLabel={(tab) => tab.title}
        getButtonProps={() => ({ 'data-testid': 'alpha-tab', className: 'custom-tab' })}
      />,
    );

    const tab = screen.getByTestId('alpha-tab');
    expect(tab).toHaveTextContent('Alpha');
    expect(tab).toHaveClass('custom-tab');
    expect(tab).toHaveAttribute('aria-selected', 'true');
  });
});
