import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import TokensSecurityTab from './TokensSecurityTab.jsx';
import {
  getLlmProxyApiKeyStatus,
  getRevealPinStatus,
} from '../services/api.js';

vi.mock('../services/api.js', () => ({
  getLlmProxyApiKeyStatus: vi.fn().mockResolvedValue({ configured: true, recoverable: true }),
  generateLlmProxyApiKey: vi.fn(),
  deleteLlmProxyApiKey: vi.fn(),
  revealLlmProxyApiKey: vi.fn(),
  getRevealPinStatus: vi.fn().mockResolvedValue({ configured: false, locked_out: false }),
  setRevealPin: vi.fn(),
  changeRevealPin: vi.fn(),
  disableRevealPin: vi.fn(),
  resetRevealPinLockout: vi.fn(),
}));

function mockHostname(hostname) {
  Object.defineProperty(window, 'location', {
    configurable: true,
    value: { hostname },
  });
}

describe('TokensSecurityTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockHostname('127.0.0.1');
    getLlmProxyApiKeyStatus.mockResolvedValue({ configured: true, recoverable: true });
    getRevealPinStatus.mockResolvedValue({ configured: false, locked_out: false });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders Tokens and Security heading', async () => {
    render(<TokensSecurityTab />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Tokens and Security/i })).toBeInTheDocument();
    });
  });

  it('fetches reveal PIN status on loopback (no stub)', async () => {
    render(<TokensSecurityTab />);
    await waitFor(() => {
      expect(getRevealPinStatus).toHaveBeenCalled();
    });
    expect(screen.getByText('Not configured', { selector: '.dashboard-kv-value' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Install PIN/i })).toBeInTheDocument();
  });

  it('shows Change PIN and Disable PIN when PIN is configured on loopback', async () => {
    getRevealPinStatus.mockResolvedValue({ configured: true, locked_out: false });
    render(<TokensSecurityTab />);
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Change PIN/i })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Disable PIN/i })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Install PIN/i })).not.toBeInTheDocument();
  });

  it('shows lockout alert and Reset Lockout on loopback when locked out', async () => {
    getRevealPinStatus.mockResolvedValue({ configured: true, locked_out: true });
    render(<TokensSecurityTab />);
    await waitFor(() => {
      expect(screen.getByRole('alert')).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Reset Lockout/i })).toBeInTheDocument();
    expect(screen.getByText(/PIN is locked/i)).toBeInTheDocument();
  });

  it('hides loopback admin buttons on LAN and shows guidance text', async () => {
    mockHostname('192.168.1.50');
    getRevealPinStatus.mockResolvedValue({ configured: false, locked_out: false });
    render(<TokensSecurityTab />);
    await waitFor(() => {
      expect(getRevealPinStatus).toHaveBeenCalled();
    });
    expect(screen.queryByRole('button', { name: /Install PIN/i })).not.toBeInTheDocument();
    expect(
      screen.getByText(/Install, change, or reset the reveal PIN from the machine where the server is running/i),
    ).toBeInTheDocument();
  });
});
