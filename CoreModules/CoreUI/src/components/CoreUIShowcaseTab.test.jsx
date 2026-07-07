import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import CoreUIShowcaseTab from './CoreUIShowcaseTab.jsx';

vi.mock('./StandByScreen.jsx', () => ({
  default: ({ moduleName }) => <div role="status">{moduleName}</div>,
}));

describe('CoreUIShowcaseTab', () => {
  it('renders the showcase inventory and changes categories', () => {
    render(<CoreUIShowcaseTab />);

    expect(screen.getByRole('heading', { name: 'CoreUI Showcase' })).toBeInTheDocument();
    expect(screen.getByRole('tablist', { name: 'Showcase categories' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Buttons' }));

    expect(screen.getByRole('tab', { name: 'Buttons' })).toHaveAttribute('aria-selected', 'true');
  });

  it('renders layout.css regression anchors in the Layout showcase', () => {
    render(<CoreUIShowcaseTab />);

    fireEvent.click(screen.getByRole('tab', { name: 'Layout & Navigation' }));

    expect(screen.getByRole('heading', { name: 'Navigation & Status' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Forms & Controls' })).toBeInTheDocument();
    expect(screen.getByText('Session Manager')).toBeInTheDocument();
    expect(screen.getByText('running')).toBeInTheDocument();
    expect(screen.getByText('checking')).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'StandByScreen' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Service status' })).toBeInTheDocument();
  });
});
