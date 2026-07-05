import { useCallback, useEffect, useMemo, useState } from 'react';
import ActionableError from '../ActionableError';
import CoreUIBadge from '../CoreUIBadge';
import CoreUIButton from '../CoreUIButton';
import EmptyState from '../EmptyState';
import M3LoadingIndicator from '../M3LoadingIndicator';
import { getHelpArticle, getHelpArticles, searchHelpArticles } from '../../services/api.js';
import { t } from '../../services/i18n.js';
import { renderHelpMarkdown } from '../../utils/helpMarkdown.js';
import {
  groupHelpArticles,
  helpArticleIcon,
  helpArticleSummary,
} from './helpArticles.js';
import '../../styles/default-card.css';
import '../../styles/components/ModelTester.css';
import '../../styles/components/HelpTab.css';

const COMPACT_BREAKPOINT = '(max-width: 859px)';

/**
 * In-app help knowledge base using Material 3 list-detail layout.
 *
 * @param {Object} props
 * @param {string|null} [props.initialSlug] - Deep-link slug from `?help=` query.
 * @param {Function} [props.onInitialSlugConsumed] - Called after initial slug is applied.
 */
export default function HelpViewer({ initialSlug = null, onInitialSlugConsumed }) {
  const [articles, setArticles] = useState([]);
  const [selectedSlug, setSelectedSlug] = useState('');
  const [article, setArticle] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState([]);
  const [loadingIndex, setLoadingIndex] = useState(true);
  const [loadingArticle, setLoadingArticle] = useState(false);
  const [error, setError] = useState('');
  const [mobilePane, setMobilePane] = useState('list');
  const [navOpen, setNavOpen] = useState(true);

  const groupedSections = useMemo(() => groupHelpArticles(articles), [articles]);

  const loadIndex = useCallback(async () => {
    setLoadingIndex(true);
    setError('');
    try {
      const data = await getHelpArticles();
      const rows = Array.isArray(data?.articles) ? data.articles : [];
      setArticles(rows);
      setSelectedSlug((prev) => {
        if (prev) return prev;
        return rows.length > 0 ? String(rows[0].slug || rows[0].id || '') : '';
      });
    } catch (err) {
      setError(err?.message || 'Failed to load help articles');
    } finally {
      setLoadingIndex(false);
    }
  }, []);

  useEffect(() => {
    void loadIndex();
  }, [loadIndex]);

  useEffect(() => {
    if (!initialSlug) return;
    setSelectedSlug(String(initialSlug));
    setMobilePane('detail');
    onInitialSlugConsumed?.();
  }, [initialSlug, onInitialSlugConsumed]);

  useEffect(() => {
    if (!selectedSlug) {
      setArticle(null);
      return undefined;
    }

    let cancelled = false;
    setLoadingArticle(true);
    setError('');

    void getHelpArticle(selectedSlug)
      .then((data) => {
        if (!cancelled) setArticle(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setArticle(null);
          setError(err?.message || 'Failed to load help article');
        }
      })
      .finally(() => {
        if (!cancelled) setLoadingArticle(false);
      });

    return () => {
      cancelled = true;
    };
  }, [selectedSlug]);

  useEffect(() => {
    const query = searchQuery.trim();
    if (!query) {
      setSearchResults([]);
      return undefined;
    }

    let cancelled = false;
    const timer = window.setTimeout(() => {
      void searchHelpArticles(query)
        .then((data) => {
          if (!cancelled) {
            setSearchResults(Array.isArray(data?.results) ? data.results : []);
          }
        })
        .catch(() => {
          if (!cancelled) setSearchResults([]);
        });
    }, 250);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [searchQuery]);

  const html = useMemo(
    () => renderHelpMarkdown(article?.content || ''),
    [article?.content],
  );

  const showSearchResults = searchQuery.trim().length > 0;

  const selectArticle = (slug) => {
    setSelectedSlug(slug);
    if (
      typeof window !== 'undefined'
      && typeof window.matchMedia === 'function'
      && window.matchMedia(COMPACT_BREAKPOINT).matches
    ) {
      setMobilePane('detail');
    }
  };

  const openSearchResult = (slug) => {
    setSearchQuery('');
    selectArticle(slug);
  };

  const clearSearch = () => {
    setSearchQuery('');
    setSearchResults([]);
  };

  return (
    <div className="help-tab tab-view">
      <header className="help-header">
        <div className="help-header__intro">
          <span className="help-kicker">Knowledge base</span>
          <h1>{t('nav.help')}</h1>
          <p className="help-lead">
            Material guides for builds, RAG, providers, extensions, and troubleshooting.
          </p>
        </div>

        <div className="help-search-bar" role="search">
          <span className="material-symbols-outlined help-search-bar__leading" aria-hidden="true">
            search
          </span>
          <input
            id="help-search-input"
            className="help-search-bar__input"
            type="search"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search help articles"
            autoComplete="off"
            aria-label="Search help articles"
          />
          {searchQuery ? (
            <button
              type="button"
              className="help-search-bar__clear"
              onClick={clearSearch}
              aria-label="Clear search"
            >
              <span className="material-symbols-outlined" aria-hidden="true">
                close
              </span>
            </button>
          ) : null}
        </div>
      </header>

      {error ? (
        <ActionableError message={error} onRetry={() => void loadIndex()} />
      ) : null}

      {loadingIndex ? (
        <section className="app-default-card help-loading-card" aria-busy="true" aria-label="Loading help topics">
          <M3LoadingIndicator size="md" />
        </section>
      ) : showSearchResults ? (
        <section className="app-default-card help-search-panel" aria-label="Help search results">
          <h2 className="help-panel-title">Search results</h2>
          {searchResults.length === 0 ? (
            <EmptyState>No articles matched your search.</EmptyState>
          ) : (
            <ul className="help-nav-list help-nav-list--search">
              {searchResults.map((row) => (
                <li key={row.slug}>
                  <button
                    type="button"
                    className="help-nav-item"
                    onClick={() => openSearchResult(row.slug)}
                  >
                    <span className="material-symbols-outlined help-nav-item__icon" aria-hidden="true">
                      {helpArticleIcon(row.slug)}
                    </span>
                    <span className="help-nav-item__text">
                      <span className="help-nav-item__headline">{row.title}</span>
                      {row.snippet ? (
                        <span className="help-nav-item__supporting">{row.snippet}</span>
                      ) : null}
                    </span>
                    <span className="material-symbols-outlined help-nav-item__trailing" aria-hidden="true">
                      chevron_right
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      ) : (
        <div
          className="help-list-detail"
          data-mobile-pane={mobilePane}
          data-nav-open={navOpen ? 'true' : 'false'}
        >
          <nav
            id="help-list-pane"
            className="app-default-card help-list-pane"
            aria-label="Help topics"
            aria-hidden={!navOpen ? 'true' : undefined}
          >
            {groupedSections.map((section) => (
              <section key={section.id} className="help-list-section">
                <p className="help-list-section__label">{section.label}</p>
                <ul className="help-nav-list">
                  {section.articles.map((row) => {
                    const slug = String(row.slug || row.id || '');
                    const active = slug === selectedSlug;
                    return (
                      <li key={slug}>
                        <button
                          type="button"
                          className={`help-nav-item${active ? ' help-nav-item--active' : ''}`}
                          aria-current={active ? 'page' : undefined}
                          onClick={() => selectArticle(slug)}
                        >
                          <span className="material-symbols-outlined help-nav-item__icon" aria-hidden="true">
                            {helpArticleIcon(slug)}
                          </span>
                          <span className="help-nav-item__text">
                            <span className="help-nav-item__headline">{row.title || slug}</span>
                            <span className="help-nav-item__supporting">{helpArticleSummary(row)}</span>
                          </span>
                          {active ? null : (
                            <span className="material-symbols-outlined help-nav-item__trailing" aria-hidden="true">
                              chevron_right
                            </span>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              </section>
            ))}
          </nav>

          <article className="app-default-card help-detail-pane" aria-live="polite">
            <div className="help-detail-toolbar">
              <CoreUIButton
                type="button"
                variant="icon"
                size="icon"
                className="help-nav-toggle"
                aria-expanded={navOpen}
                aria-controls="help-list-pane"
                aria-label={navOpen ? 'Hide topics menu' : 'Show topics menu'}
                onClick={() => setNavOpen((open) => !open)}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  {navOpen ? 'left_panel_close' : 'left_panel_open'}
                </span>
              </CoreUIButton>
              <button
                type="button"
                className="help-detail-back"
                onClick={() => setMobilePane('list')}
              >
                <span className="material-symbols-outlined" aria-hidden="true">
                  arrow_back
                </span>
                Topics
              </button>
            </div>

            {loadingArticle ? (
              <div className="help-loading-card" aria-busy="true">
                <M3LoadingIndicator size="md" />
              </div>
            ) : article ? (
              <>
                <header className="help-detail-header">
                  <div className="help-detail-header__icon-wrap" aria-hidden="true">
                    <span className="material-symbols-outlined help-detail-header__icon">
                      {helpArticleIcon(article.slug)}
                    </span>
                  </div>
                  <div className="help-detail-header__copy">
                    <h2 className="help-detail-title">{article.title}</h2>
                    {Array.isArray(article.tags) && article.tags.length > 0 ? (
                      <div className="help-tags">
                        {article.tags.map((tag) => (
                          <CoreUIBadge key={tag} tone="info">
                            {tag}
                          </CoreUIBadge>
                        ))}
                      </div>
                    ) : null}
                  </div>
                </header>
                <div className="help-detail-divider" aria-hidden="true" />
                <div
                  className="markdown-prose markdown-prose--preview help-article-body"
                  dangerouslySetInnerHTML={{ __html: html }}
                />
              </>
            ) : (
              <EmptyState>Select a help topic to read the guide.</EmptyState>
            )}
          </article>
        </div>
      )}
    </div>
  );
}
