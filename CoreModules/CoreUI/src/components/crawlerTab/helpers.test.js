import { describe, expect, it, vi, afterEach } from 'vitest';
import {
  exportMdPreview,
  formatDate,
  formatMdPreviewSize,
  getDefaultParamsForStepType,
  getMdPreviewSize,
  getMdPreviewText,
} from './helpers.js';

describe('crawlerTab helpers', () => {
  describe('formatDate', () => {
    it('returns Never for empty input', () => {
      expect(formatDate(null)).toBe('Never');
      expect(formatDate('')).toBe('Never');
    });

    it('formats valid ISO timestamps', () => {
      const formatted = formatDate('2026-06-16T12:00:00.000Z');
      expect(formatted).not.toBe('Never');
      expect(formatted).toMatch(/2026/);
    });
  });

  describe('getDefaultParamsForStepType', () => {
    it('returns step-specific defaults', () => {
      expect(getDefaultParamsForStepType('delete_lines_exact')).toEqual({
        lines: [],
        case_sensitive: false,
      });
      expect(getDefaultParamsForStepType('wrap_indented_code')).toEqual({
        language: 'swift',
        min_block_lines: 2,
      });
    });

    it('returns empty object for unknown step types', () => {
      expect(getDefaultParamsForStepType('unknown_step')).toEqual({});
    });
  });

  describe('MD preview helpers', () => {
    it('extracts processed markdown text and byte size', () => {
      const preview = { processed_md: '# Hello\nworld' };
      expect(getMdPreviewText(preview)).toBe('# Hello\nworld');
      expect(getMdPreviewSize(preview)).toBeGreaterThan(0);
    });

    it('formats preview sizes for B, KB, and MB', () => {
      expect(formatMdPreviewSize(512)).toBe('512 B');
      expect(formatMdPreviewSize(2048)).toBe('2.0 KB');
      expect(formatMdPreviewSize(2 * 1024 * 1024)).toBe('2.00 MB');
    });

    it('exports markdown as downloadable blob link', () => {
      const createObjectURL = vi.fn().mockReturnValue('blob:test');
      const revokeObjectURL = vi.fn();
      vi.stubGlobal('URL', {
        createObjectURL,
        revokeObjectURL,
      });
      const click = vi.fn();
      const remove = vi.fn();
      const link = { href: '', download: '', click, remove };
      vi.spyOn(document, 'createElement').mockReturnValue(link);
      vi.spyOn(document.body, 'appendChild').mockImplementation(() => {});

      exportMdPreview({ processed_md: '# Preview' }, 'notes');

      expect(link.download).toBe('notes.md');
      expect(click).toHaveBeenCalledOnce();
      expect(revokeObjectURL).toHaveBeenCalledWith('blob:test');

      vi.unstubAllGlobals();
    });
  });
});
