import { describe, expect, it } from 'vitest';
import { notificationModuleLabel } from './notificationModuleLabels.js';

describe('notificationModuleLabel', () => {
  it('maps known module keys to display labels', () => {
    expect(notificationModuleLabel('crawler')).toBe('Crawler / Indexer');
    expect(notificationModuleLabel('rag-tests')).toBe('RAG Tests');
    expect(notificationModuleLabel('dumb-proxy')).toBe('RAG Fusion Proxy');
  });

  it('title-cases unknown hyphenated keys', () => {
    expect(notificationModuleLabel('my-feature')).toBe('My Feature');
  });

  it('falls back to CoreUI for empty input', () => {
    expect(notificationModuleLabel('')).toBe('CoreUI');
    expect(notificationModuleLabel(null)).toBe('CoreUI');
  });
});
