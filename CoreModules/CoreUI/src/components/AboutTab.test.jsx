import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import AboutTab from '../components/AboutTab.jsx';

vi.mock('../services/api.js', () => ({
  getVersion: vi.fn().mockResolvedValue({
    app_name: 'chironai',
    display_name: 'ChironAI',
    version: '1.2.3',
    stage: 'stable',
  }),
}));

describe('AboutTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders project icon, name and version', async () => {
    render(<AboutTab appVersion="1.0.0" />);
    expect(screen.getByRole('heading', { level: 1, name: /About ChironAI/i })).toBeInTheDocument();
    expect(screen.getByAltText(/ChironAI project icon/i)).toBeInTheDocument();
    expect(await screen.findByRole('heading', { level: 2, name: /ChironAI/i })).toBeInTheDocument();
    expect(await screen.findByText(/Version 1\.2\.3/i)).toBeInTheDocument();
  });
});
