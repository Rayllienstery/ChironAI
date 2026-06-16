import { describe, expect, it } from 'vitest';
import { renderTesterMarkdown } from './modelTesterMarkdown.js';

describe('modelTesterMarkdown', () => {
  it('renders markdown paragraphs to sanitized HTML', () => {
    const html = renderTesterMarkdown('Hello **world**');
    expect(html).toContain('<strong>world</strong>');
    expect(html).not.toContain('<script');
  });

  it('highlights fenced code blocks', () => {
    const html = renderTesterMarkdown('```js\nconst x = 1;\n```');
    expect(html).toContain('hljs');
    expect(html).toContain('const');
  });

  it('strips unsafe HTML from assistant output', () => {
    const html = renderTesterMarkdown('<img src=x onerror=alert(1)>');
    expect(html).not.toMatch(/onerror/i);
  });
});
