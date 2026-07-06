import { describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen } from '@testing-library/react';
import InfoButton from './InfoButton.jsx';
import { HelpPanelProvider } from '../help/HelpPanelContext.jsx';

vi.mock('../help/HelpPanel.jsx', () => ({
  default: ({ open, slug, label }) => (open ? <div data-testid="help-panel">{slug}:{label}</div> : null),
}));

function renderWithHelp(ui) {
  return render(<HelpPanelProvider>{ui}</HelpPanelProvider>);
}

describe('InfoButton', () => {
  it('opens the help panel with parsed slug', () => {
    renderWithHelp(<InfoButton helpRef="builds#generation-params" label="Temperature" />);

    fireEvent.click(screen.getByRole('button', { name: 'Help: Temperature' }));

    expect(screen.getByTestId('help-panel')).toHaveTextContent('builds:Temperature');
  });
});
