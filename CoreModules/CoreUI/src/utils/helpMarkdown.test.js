import { describe, expect, it } from 'vitest';
import { renderHelpMarkdown } from './helpMarkdown.js';

describe('helpMarkdown', () => {
  it('strips the lead h1 and renders body markup', () => {
    const html = renderHelpMarkdown('# Title\n\nHello **world**.\n\n<script>alert(1)</script>');
    expect(html).not.toContain('<h1');
    expect(html).not.toContain('Title');
    expect(html).toContain('<strong>world</strong>');
    expect(html).not.toContain('<script');
  });

  it('keeps h2 sections when lead title is removed', () => {
    const html = renderHelpMarkdown('# Doc\n\n## Section\n\nBody text.');
    expect(html).toContain('<h2');
    expect(html).toContain('Section');
    expect(html).not.toContain('<h1');
  });

  it('adds slug ids to headings for anchor navigation', () => {
    const html = renderHelpMarkdown('# Doc\n\n## Context limits\n\nBody.');
    expect(html).toContain('id="context-limits"');
  });
});
