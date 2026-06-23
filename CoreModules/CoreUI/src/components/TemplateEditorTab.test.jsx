import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPrompt, getPromptContent, getPrompts, getTrashPrompts } from '../services/api.js';
import TemplateEditorTab from './TemplateEditorTab.jsx';

vi.mock('../services/api.js', () => ({
  clearTrash: vi.fn().mockResolvedValue({ ok: true }),
  createPrompt: vi.fn().mockResolvedValue({ ok: true }),
  deletePrompt: vi.fn().mockResolvedValue({ ok: true }),
  getPromptContent: vi.fn().mockResolvedValue({
    content: '# Adapter Prompt\nShort description\nUse adapters carefully.',
  }),
  getPrompts: vi.fn().mockResolvedValue({
    prompts: [{ name: 'README' }, { name: 'adapter.md' }],
  }),
  getTrashPromptContent: vi.fn().mockResolvedValue({ content: '# Deleted' }),
  getTrashPrompts: vi.fn().mockResolvedValue({ prompts: [] }),
  restorePrompt: vi.fn().mockResolvedValue({ ok: true }),
  updatePrompt: vi.fn().mockResolvedValue({ ok: true }),
  updateTrashPrompt: vi.fn().mockResolvedValue({ ok: true }),
}));

describe('TemplateEditorTab', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(window, 'confirm').mockReturnValue(true);
  });

  it('loads prompt templates and opens selected prompt content', async () => {
    render(<TemplateEditorTab />);

    await waitFor(() => {
      expect(screen.getByText('adapter.md')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('adapter.md'));

    await waitFor(() => {
      expect(getPromptContent).toHaveBeenCalledWith('adapter.md');
    });
    expect(screen.getByDisplayValue('Adapter Prompt')).toBeInTheDocument();
    expect(screen.getByDisplayValue('Use adapters carefully.')).toBeInTheDocument();
  });

  it('creates a new template from the empty editor state', async () => {
    render(<TemplateEditorTab />);

    await waitFor(() => {
      expect(getPrompts).toHaveBeenCalled();
    });

    fireEvent.click(screen.getByTitle('Create new template'));
    fireEvent.change(screen.getByPlaceholderText('Enter template name...'), {
      target: { value: 'new-template.md' },
    });
    fireEvent.click(screen.getByRole('button', { name: 'Create' }));

    await waitFor(() => {
      expect(createPrompt).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'new-template.md' }),
      );
    });
    expect(getTrashPrompts).not.toHaveBeenCalled();
  });
});
