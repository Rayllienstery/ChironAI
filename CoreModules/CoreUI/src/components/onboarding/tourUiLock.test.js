import { describe, expect, it, beforeEach, afterEach } from 'vitest';
import { releaseBodyScrollLock } from './tourUiLock.js';

describe('tourUiLock', () => {
  beforeEach(() => {
    document.body.style.overflow = 'hidden';
  });

  afterEach(() => {
    releaseBodyScrollLock();
  });

  it('clears the body overflow lock', () => {
    releaseBodyScrollLock();
    expect(document.body.style.overflow).toBe('');
  });
});
