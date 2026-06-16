import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import ExtensionsTab from './ExtensionsTab.jsx';

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
  });

  it('renders Extensions heading', async () => {
    render(<ExtensionsTab />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Extensions/i })).toBeInTheDocument();
    });
  });
});
