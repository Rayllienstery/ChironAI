import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import SettingsTab from './SettingsTab.jsx';

vi.mock('../services/api.js', () => ({
  getSettings: vi.fn().mockResolvedValue({ theme_mode: 'system' }),
  updateSettings: vi.fn().mockResolvedValue({ ok: true }),
}));

describe('SettingsTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Settings heading', async () => {
    render(
      <SettingsTab
        themeMode="system"
        lightAccent="purple"
        darkAccent="cyan"
        onThemeChange={vi.fn()}
        onAppSettingsSaved={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Settings/i })).toBeInTheDocument();
    });
  });
});
