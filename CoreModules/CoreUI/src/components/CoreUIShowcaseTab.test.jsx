import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import CoreUIShowcaseTab from './CoreUIShowcaseTab.jsx';

describe('CoreUIShowcaseTab', () => {
  it('renders the showcase inventory and changes categories', () => {
    render(<CoreUIShowcaseTab />);

    expect(screen.getByRole('heading', { name: 'CoreUI Showcase' })).toBeInTheDocument();
    expect(screen.getByRole('tablist', { name: 'Showcase categories' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: 'Buttons' }));

    expect(screen.getByRole('tab', { name: 'Buttons' })).toHaveAttribute('aria-selected', 'true');
  });
});
