import { describe, expect, it } from 'vitest';
import { renderHelpMarkdown } from './helpMarkdown.js';

describe('helpMarkdown', () => {
  it('renders headings and sanitizes script tags', () => {
    const html = renderHelpMarkdown('# Title\n\nHello **world**.\n\n<script>alert(1)</script>');
    expect(html).toContain('<h1');
    expect(html).toContain('Title');
    expect(html).toContain('<strong>world</strong>');
    expect(html).not.toContain('<script');
  });
});
