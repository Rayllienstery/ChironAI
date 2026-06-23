import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { getRagCollections, getRagTests, runRagTesterV2 } from '../services/api.js';
import RagTesterV2Tab from './RagTesterV2Tab.jsx';

vi.mock('../services/api.js', () => ({
  cancelRagTesterV2Run: vi.fn().mockResolvedValue({ ok: true }),
  getRagCollections: vi.fn().mockResolvedValue({
    collections: [{ name: 'docs', points_count: 12 }],
  }),
  getRagTesterV2RunStatus: vi.fn().mockResolvedValue({
    status: 'completed',
    results: [],
    progress: { current_index: 1, total: 1 },
  }),
  getRagTests: vi.fn().mockResolvedValue({
    filters: { platform: ['ios'], framework: ['swiftui'], difficulty: ['easy'] },
    tests: [
      {
        id: 'rag-1',
        name: 'Find adapter docs',
        question: 'Where are adapters documented?',
        platform: 'ios',
        framework: 'swiftui',
        difficulty: 'easy',
      },
    ],
  }),
  runRagTesterV2: vi.fn().mockResolvedValue({ job_id: 'job-1' }),
}));

describe('RagTesterV2Tab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it('loads tests and can start a selected retrieval run', async () => {
    render(<RagTesterV2Tab />);

    expect(screen.getByRole('heading', { name: 'Rag Tester V2' })).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText('Find adapter docs')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByLabelText('Select Find adapter docs'));
    fireEvent.click(screen.getByRole('button', { name: 'Run selected' }));

    await waitFor(() => {
      expect(runRagTesterV2).toHaveBeenCalledWith(
        expect.objectContaining({
          collection_name: 'docs',
          test_ids: ['rag-1'],
        }),
      );
    });
    expect(getRagCollections).toHaveBeenCalled();
    expect(getRagTests).toHaveBeenCalled();
  });
});
