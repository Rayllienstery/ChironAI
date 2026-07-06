import { render } from '@testing-library/react';
import { HelpPanelProvider } from '../components/help/HelpPanelContext.jsx';

export function renderWithProviders(ui, options) {
  return render(<HelpPanelProvider>{ui}</HelpPanelProvider>, options);
}
