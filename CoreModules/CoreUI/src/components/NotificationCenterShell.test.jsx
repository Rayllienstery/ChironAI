import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import NotificationCenterShell from './NotificationCenterShell.jsx';

const liveActivities = new Map([
  [
    'live-1',
    {
      source: 'rag',
      node: <div>Indexing collection</div>,
      headerLeading: <span data-testid="header-leading">⏳</span>,
    },
  ],
]);

vi.mock('./NotificationCenterContext', () => ({
  useNotificationCenter: () => ({
    sessionId: 'test-session',
    persisted: [],
    liveActivities,
    dismissPersisted: vi.fn(),
    dismissPersistedMany: vi.fn(),
    clearPersisted: vi.fn(),
    suppressLiveActivity: vi.fn(),
  }),
}));

describe('NotificationCenterShell', () => {
  beforeEach(() => {
    globalThis.ResizeObserver = class ResizeObserver {
      observe() {}
      unobserve() {}
      disconnect() {}
    };
  });

  it('renders headerLeading for live activity cards', () => {
    render(<NotificationCenterShell />);

    expect(screen.getByTestId('header-leading')).toBeInTheDocument();
    expect(screen.getByText('Indexing collection')).toBeInTheDocument();
    expect(
      document.querySelector('.notification-center-card-header-title--with-leading'),
    ).toBeTruthy();
  });
});
