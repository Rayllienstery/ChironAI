import { describe, expect, it } from 'vitest';
import { buildFieldHelpRef, buildSectionHelpRef } from './buildFieldHelp.js';

describe('buildFieldHelp', () => {
  it('maps known build fields to help slugs', () => {
    expect(buildFieldHelpRef('rag_collection')).toBe('rag-collections');
    expect(buildFieldHelpRef('temperature')).toBe('builds#generation-params');
  });

  it('maps section labels to help slugs', () => {
    expect(buildSectionHelpRef('RAG')).toBe('rag-collections');
    expect(buildSectionHelpRef('Web')).toBe('builds#web-interaction');
  });

  it('returns empty string for unknown keys', () => {
    expect(buildFieldHelpRef('not-a-field')).toBe('');
  });
});
