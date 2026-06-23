import { marked } from 'marked';
import { markedHighlight } from 'marked-highlight';
import hljs from 'highlight.js/lib/common';
import DOMPurify from 'dompurify';

marked.use(
  markedHighlight({
    emptyLangClass: 'hljs',
    langPrefix: 'hljs language-',
    highlight(code, lang) {
      const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext';
      try {
        return hljs.highlight(code, { language }).value;
      } catch {
        return hljs.highlight(code, { language: 'plaintext' }).value;
      }
    },
  })
);

marked.setOptions({
  gfm: true,
  breaks: true,
});

/**
 * Parse assistant markdown to sanitized HTML (syntax-highlighted fenced blocks).
 */
export function renderTesterMarkdown(content) {
  const raw = marked.parse(typeof content === 'string' ? content : '');
  return DOMPurify.sanitize(raw);
}
