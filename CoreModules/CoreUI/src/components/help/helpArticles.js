/** M3 list-detail sections and icons for in-app Help articles. */

export const HELP_SECTIONS = [
  {
    id: 'start',
    label: 'Getting started',
    slugs: ['getting-started'],
  },
  {
    id: 'platform',
    label: 'Platform',
    slugs: ['builds', 'rag-collections', 'proxy-clients', 'providers'],
  },
  {
    id: 'workflow',
    label: 'Workflow',
    slugs: ['extensions', 'indexing'],
  },
  {
    id: 'support',
    label: 'Support',
    slugs: ['logs-debugging', 'troubleshooting'],
  },
];

const HELP_ARTICLE_ICONS = {
  'getting-started': 'flag',
  builds: 'hub',
  'rag-collections': 'library_books',
  'proxy-clients': 'api',
  providers: 'cloud',
  extensions: 'extension',
  indexing: 'sync',
  'logs-debugging': 'manage_search',
  troubleshooting: 'build_circle',
};

export function groupHelpArticles(articles) {
  const bySlug = new Map(
    (articles || []).map((row) => [String(row.slug || row.id || ''), row]),
  );

  return HELP_SECTIONS.map((section) => ({
    ...section,
    articles: section.slugs
      .map((slug) => bySlug.get(slug))
      .filter(Boolean),
  })).filter((section) => section.articles.length > 0);
}

export function helpArticleIcon(slug) {
  return HELP_ARTICLE_ICONS[String(slug || '')] || 'article';
}

export function helpArticleSummary(article) {
  const tags = Array.isArray(article?.tags) ? article.tags.filter(Boolean) : [];
  if (tags.length > 0) return tags.slice(0, 3).join(' · ');
  return 'Guide';
}
