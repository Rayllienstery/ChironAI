import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import DockerTab from './DockerTab.jsx';

vi.mock('../services/api.js', () => ({
  getDockerStatus: vi.fn().mockResolvedValue({ available: true, version: '26.0.0' }),
  getDockerContainers: vi.fn().mockResolvedValue({ containers: [] }),
  getDockerImages: vi.fn().mockResolvedValue({ images: [] }),
  startDockerContainer: vi.fn(),
  stopDockerContainer: vi.fn(),
  removeDockerContainer: vi.fn(),
  removeDockerImage: vi.fn(),
  checkDockerImageUpdate: vi.fn(),
  updateDockerImage: vi.fn(),
}));

describe('DockerTab smoke', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders Docker heading', async () => {
    render(<DockerTab />);
    await waitFor(() => {
      expect(screen.getByRole('heading', { level: 2, name: /Docker/i })).toBeInTheDocument();
    });
  });
});
