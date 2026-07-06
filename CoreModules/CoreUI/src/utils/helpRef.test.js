import { describe, expect, it } from 'vitest';
import { parseHelpRef } from './helpRef.js';

describe('helpRef', () => {
  it('parses slug-only references', () => {
    expect(parseHelpRef('builds')).toEqual({ slug: 'builds', anchor: '' });
  });

  it('parses slug and anchor', () => {
    expect(parseHelpRef('rag-collections#limits')).toEqual({
      slug: 'rag-collections',
      anchor: 'limits',
    });
  });

  it('normalizes casing and whitespace', () => {
    expect(parseHelpRef(' Builds#Generation-Params ')).toEqual({
      slug: 'builds',
      anchor: 'generation-params',
    });
  });
});
