import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  confirmCloudRagRun,
  groundingOverlap,
  isTransientFetchLikeError,
  loadLastUsedRagTestsSettings,
  metricVersionLabel,
  ragRetrieved,
  sortModelsCloudFirst,
  strictRagOk,
  yesNo,
} from './helpers.js';
import { RAG_TESTS_LAST_USED_KEY } from './constants.js';

describe('ragTestsTab helpers', () => {
  describe('ragRetrieved', () => {
    it('prefers retrieval_used when present', () => {
      expect(ragRetrieved({ retrieval_used: false, rag_used: true })).toBe(false);
      expect(ragRetrieved({ retrieval_used: true, rag_used: false })).toBe(true);
    });

    it('falls back to rag_used when retrieval_used is null', () => {
      expect(ragRetrieved({ retrieval_used: null, rag_used: true })).toBe(true);
      expect(ragRetrieved({ rag_used: false })).toBe(false);
    });

    it('returns false for missing row', () => {
      expect(ragRetrieved(null)).toBe(false);
    });
  });

  describe('groundingOverlap and strictRagOk', () => {
    it('detects grounding overlap flag', () => {
      expect(groundingOverlap({ grounding_overlap: true })).toBe(true);
      expect(groundingOverlap({ grounding_overlap: false })).toBe(false);
    });

    it('detects strict RAG pass flag', () => {
      expect(strictRagOk({ strict_rag_ok: true })).toBe(true);
      expect(strictRagOk({})).toBe(false);
    });
  });

  describe('yesNo and metricVersionLabel', () => {
    it('formats yes/no/dash', () => {
      expect(yesNo(true)).toBe('Yes');
      expect(yesNo(false)).toBe('No');
      expect(yesNo(null)).toBe('-');
    });

    it('labels metrics version with legacy fallback', () => {
      expect(metricVersionLabel({ metrics_version: 'v2' })).toBe('v2');
      expect(metricVersionLabel({})).toBe('legacy_unknown');
    });
  });

  describe('sortModelsCloudFirst', () => {
    it('groups cloud-tagged models first alphabetically', () => {
      const sorted = sortModelsCloudFirst([
        { id: 'local-7b' },
        { id: 'gpt-4:cloud' },
        { id: 'alpha:cloud' },
      ]);
      expect(sorted.map((m) => m.id)).toEqual(['alpha:cloud', 'gpt-4:cloud', 'local-7b']);
    });
  });

  describe('isTransientFetchLikeError', () => {
    it('recognizes browser fetch failures', () => {
      expect(isTransientFetchLikeError('Failed to fetch')).toBe(true);
      expect(isTransientFetchLikeError('NetworkError when attempting to fetch resource.')).toBe(true);
      expect(isTransientFetchLikeError('Validation failed')).toBe(false);
    });
  });

  describe('confirmCloudRagRun', () => {
    it('skips confirm for non-cloud models', () => {
      const confirmSpy = vi.spyOn(window, 'confirm');
      expect(confirmCloudRagRun('llama3:local')).toBe(true);
      expect(confirmSpy).not.toHaveBeenCalled();
      confirmSpy.mockRestore();
    });

    it('asks confirm for cloud-tagged models', () => {
      const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
      expect(confirmCloudRagRun('gpt-4:cloud')).toBe(false);
      expect(confirmSpy).toHaveBeenCalledOnce();
      confirmSpy.mockRestore();
    });
  });

  describe('loadLastUsedRagTestsSettings', () => {
    beforeEach(() => {
      window.localStorage.clear();
    });

    afterEach(() => {
      window.localStorage.clear();
    });

    it('returns parsed settings from localStorage', () => {
      window.localStorage.setItem(
        RAG_TESTS_LAST_USED_KEY,
        JSON.stringify({ collection: 'docs', model: 'llama3' }),
      );
      expect(loadLastUsedRagTestsSettings()).toEqual({ collection: 'docs', model: 'llama3' });
    });

    it('returns empty object for invalid JSON', () => {
      window.localStorage.setItem(RAG_TESTS_LAST_USED_KEY, 'not-json');
      expect(loadLastUsedRagTestsSettings()).toEqual({});
    });
  });
});
