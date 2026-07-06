import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({
  gfm: true,
  breaks: true,
});

function slugifyHeading(text) {
  return String(text || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

function injectHeadingIds(html) {
  return String(html || '').replace(/<h([23])(?![^>]*\bid=)([^>]*)>([^<]+)<\/h\1>/gi, (_match, level, attrs, text) => {
    const id = slugifyHeading(text);
    if (!id) return _match;
    return `<h${level}${attrs} id="${id}">${text}</h${level}>`;
  });
}

/**
 * Parse help markdown to sanitized HTML for in-app Help articles.
 * Strips the leading # title — the Help detail header already shows it.
 */
export function renderHelpMarkdown(content) {
  const text = typeof content === 'string' ? content : '';
  const withoutLeadTitle = text.replace(/^\s*#\s+[^\n]*\n+/, '');
  const raw = marked.parse(withoutLeadTitle);
  return DOMPurify.sanitize(injectHeadingIds(raw));
}
