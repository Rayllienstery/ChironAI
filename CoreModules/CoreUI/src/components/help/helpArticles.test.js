import { describe, expect, it } from 'vitest';
import {
  HELP_SECTIONS,
  groupHelpArticles,
  helpArticleIcon,
  helpArticleSummary,
} from './helpArticles.js';

describe('helpArticles', () => {
  it('groups articles into M3 sections', () => {
    const rows = [
      { slug: 'getting-started', title: 'Getting Started', tags: ['intro'] },
      { slug: 'builds', title: 'Builds', tags: ['builds'] },
      { slug: 'troubleshooting', title: 'Troubleshooting', tags: ['errors'] },
    ];

    const grouped = groupHelpArticles(rows);

    expect(grouped).toHaveLength(3);
    expect(grouped[0].label).toBe('Getting started');
    expect(grouped[0].articles[0].slug).toBe('getting-started');
    expect(grouped[1].articles.some((row) => row.slug === 'builds')).toBe(true);
  });

  it('returns icons and tag summaries for list items', () => {
    expect(helpArticleIcon('builds')).toBe('hub');
    expect(helpArticleIcon('unknown')).toBe('article');
    expect(helpArticleSummary({ tags: ['a', 'b', 'c', 'd'] })).toBe('a · b · c');
    expect(HELP_SECTIONS.length).toBeGreaterThan(0);
  });
});
