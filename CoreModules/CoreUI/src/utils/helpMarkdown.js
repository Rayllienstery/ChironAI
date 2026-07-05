import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({
  gfm: true,
  breaks: true,
});

/**
 * Parse help markdown to sanitized HTML for in-app Help articles.
 */
export function renderHelpMarkdown(content) {
  const raw = marked.parse(typeof content === 'string' ? content : '');
  return DOMPurify.sanitize(raw);
}
