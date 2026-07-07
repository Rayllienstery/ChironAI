import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import WelcomeNotificationBridge from './WelcomeNotificationBridge.jsx';
import { getVersion } from '../services/api.js';

const persistNotification = vi.fn().mockResolvedValue(undefined);

vi.mock('../services/api.js', () => ({
  getVersion: vi.fn(),
}));

vi.mock('./NotificationCenterContext', () => ({
  useNotificationCenter: () => ({ persistNotification }),
}));

describe('WelcomeNotificationBridge', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
  });

  it('uses API display_name for the welcome notification title', async () => {
    getVersion.mockResolvedValue({
      version: '0.8.32',
      display_name: 'Chiron AI STABLE 0.8.32',
      changelog: '### Added\n- Example',
    });

    render(<WelcomeNotificationBridge />);

    await waitFor(() => {
      expect(persistNotification).toHaveBeenCalledWith(
        expect.objectContaining({
          title: 'Chiron AI STABLE 0.8.32',
          source: 'system',
        }),
      );
    });
  });

  it('does not show a welcome notification when display_name is missing', async () => {
    getVersion.mockResolvedValue({
      version: '0.8.32',
      app_name: 'Chiron AI',
      changelog: '### Added\n- Example',
    });

    render(<WelcomeNotificationBridge />);

    await waitFor(() => {
      expect(getVersion).toHaveBeenCalled();
    });
    expect(persistNotification).not.toHaveBeenCalled();
  });
});
