import { describe, expect, it, vi, beforeEach } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import SettingsTab from './SettingsTab.jsx';

vi.mock('../services/api.js', () => ({
  getSettings: vi.fn().mockResolvedValue({ theme_mode: 'system' }),
  updateSettings: vi.fn().mockResolvedValue({ ok: true }),
}));

describe('SettingsTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('renders Settings heading', async () => {
    render(
      <SettingsTab
        themeMode="system"
        lightAccent="purple"
        darkAccent="cyan"
        locale="en"
        onThemeChange={vi.fn()}
        onLocaleChange={vi.fn()}
        onAppSettingsSaved={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Settings/i })).toBeInTheDocument();
    });
  });

  it('persists selected interface language and notifies the shell', async () => {
    const onLocaleChange = vi.fn();

    render(
      <SettingsTab
        themeMode="system"
        lightAccent="purple"
        darkAccent="cyan"
        locale="en"
        onThemeChange={vi.fn()}
        onLocaleChange={onLocaleChange}
        onAppSettingsSaved={vi.fn()}
      />,
    );

    const select = await screen.findByLabelText(/interface language/i);
    fireEvent.change(select, { target: { value: 'ru' } });

    expect(localStorage.getItem('chironai_locale')).toBe('ru');
    expect(onLocaleChange).toHaveBeenCalledWith('ru');
  });
});
