import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import TestingTab from './TestingTab.jsx';

vi.mock('../services/moduleTimings.js', () => ({
  loadTrackedModule: (_key, importer) => importer(),
}));

vi.mock('./ModelTester.jsx', () => ({
  default: () => <div data-testid="model-tester-stub">Model Tester</div>,
}));

describe('TestingTab smoke', () => {
  it('renders Testing heading', () => {
    render(<TestingTab sessionId="test-session" />);
    expect(screen.getByRole('heading', { level: 2, name: /Testing/i })).toBeInTheDocument();
  });
});
