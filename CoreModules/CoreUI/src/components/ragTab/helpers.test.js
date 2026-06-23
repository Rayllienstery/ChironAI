import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { CHIRONAI_RAG_TRACE_STORAGE_KEY } from '../RagTraceTimeline.jsx';
import {
  capitalize,
  persistMirroredRagTraceToStorage,
  readMirroredRagTraceFromStorage,
  wordsInMultipleCollections,
} from './helpers.js';

describe('ragTab helpers', () => {
  describe('wordsInMultipleCollections', () => {
    it('finds keywords shared across collections', () => {
      const collections = [
        { id: 'docs', keywords: ['Swift', 'API'] },
        { id: 'wiki', keywords: ['swift', 'guide'] },
      ];
      expect(wordsInMultipleCollections(collections)).toEqual(['swift']);
    });

    it('ignores empty keywords', () => {
      const collections = [{ id: 'a', keywords: ['', '  '] }];
      expect(wordsInMultipleCollections(collections)).toEqual([]);
    });
  });

  describe('capitalize', () => {
    it('capitalizes first letter and lowercases the rest', () => {
      expect(capitalize('sWIFT')).toBe('Swift');
      expect(capitalize('')).toBe('');
    });
  });

  describe('readMirroredRagTraceFromStorage', () => {
    beforeEach(() => {
      sessionStorage.clear();
    });

    afterEach(() => {
      sessionStorage.clear();
    });

    it('returns trace steps when session storage has valid payload', () => {
      sessionStorage.setItem(
        CHIRONAI_RAG_TRACE_STORAGE_KEY,
        JSON.stringify({ trace: [{ id: 'query_prep' }], latencyMs: 120 }),
      );
      expect(readMirroredRagTraceFromStorage()).toEqual({
        steps: [{ id: 'query_prep' }],
        latencyMs: 120,
      });
    });

    it('returns null for empty or invalid storage', () => {
      sessionStorage.setItem(CHIRONAI_RAG_TRACE_STORAGE_KEY, '{bad json');
      expect(readMirroredRagTraceFromStorage()).toBeNull();
    });
  });

  describe('persistMirroredRagTraceToStorage', () => {
    beforeEach(() => {
      sessionStorage.clear();
    });

    afterEach(() => {
      sessionStorage.clear();
    });

    it('writes trace payload for Rag tab mirror', () => {
      persistMirroredRagTraceToStorage([{ id: 'embed_search_pass1' }], 42);
      expect(readMirroredRagTraceFromStorage()).toEqual({
        steps: [{ id: 'embed_search_pass1' }],
        latencyMs: 42,
      });
    });

    it('ignores empty trace arrays', () => {
      persistMirroredRagTraceToStorage([]);
      expect(sessionStorage.getItem(CHIRONAI_RAG_TRACE_STORAGE_KEY)).toBeNull();
    });
  });
});
