import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ExtensionsTab from './ExtensionsTab.jsx';
import {
  getExtensionInstalled,
  getExtensionProviders,
  getExtensionRegistry,
  getExtensionUiPayload,
} from '../services/api.js';

vi.mock('../services/api.js', () => ({
  getExtensionInstalled: vi.fn().mockResolvedValue({ extensions: [] }),
  getExtensionRegistry: vi.fn().mockResolvedValue({ extensions: [] }),
  getExtensionProviders: vi.fn().mockResolvedValue({ providers: [] }),
  getExtensionDetails: vi.fn().mockResolvedValue({}),
  getExtensionUiPayload: vi.fn().mockResolvedValue({}),
  enableExtension: vi.fn(),
  disableExtension: vi.fn(),
  installExtension: vi.fn(),
  installExtensionTarget: vi.fn(),
  removeExtension: vi.fn(),
  restartExtensionSandbox: vi.fn(),
  killExtensionSandbox: vi.fn(),
  updateExtensionDocker: vi.fn(),
  checkDockerImageUpdate: vi.fn(),
  updateDockerImage: vi.fn(),
}));

describe('ExtensionsTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    getExtensionInstalled.mockResolvedValue({ extensions: [] });
    getExtensionRegistry.mockResolvedValue({ extensions: [] });
    getExtensionProviders.mockResolvedValue({ providers: [] });
    getExtensionUiPayload.mockResolvedValue({});
  });

  it('renders Extensions heading', async () => {
    render(<ExtensionsTab />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Extensions/i })).toBeInTheDocument();
    });
  });

  it('renders installed extensions before slower UI payload finishes', async () => {
    let resolveUiPayload;
    getExtensionInstalled
      .mockResolvedValueOnce({
        extensions: [
          {
            id: 'fast-extension',
            title: 'Fast Extension',
            version: '1.0.0',
            enabled: true,
            status: 'installed',
          },
        ],
      })
      .mockResolvedValueOnce({
        extensions: [
          {
            id: 'fast-extension',
            title: 'Fast Extension',
            version: '1.0.0',
            enabled: true,
            status: 'installed',
          },
        ],
      });
    getExtensionUiPayload.mockReturnValue(
      new Promise((resolve) => {
        resolveUiPayload = resolve;
      })
    );

    render(<ExtensionsTab />);

    expect(await screen.findByText('Fast Extension')).toBeInTheDocument();

    resolveUiPayload({ extensions: [], failed: [] });
    await waitFor(() => {
      expect(getExtensionUiPayload).toHaveBeenCalled();
    });
  });
});
