import { useEffect, useMemo, useRef, useState } from 'react';
import CoreUIButton from '../CoreUIButton';
import M3LoadingIndicator from '../M3LoadingIndicator';
import ActionableError from '../ActionableError';
import { getHelpArticle } from '../../services/api.js';
import { t } from '../../services/i18n';
import { renderHelpMarkdown } from '../../utils/helpMarkdown.js';
import { helpArticleIcon } from './helpArticles.js';
import '../../styles/components/HelpPanel.css';

/**
 * Slide-in contextual help drawer for field-level documentation.
 */
export default function HelpPanel({
  open,
  slug,
  anchor = '',
  label = '',
  onClose,
  onOpenFullHelp,
}) {
  const bodyRef = useRef(null);
  const [article, setArticle] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!open || !slug) {
      setArticle(null);
      setError('');
      return undefined;
    }

    let cancelled = false;
    setLoading(true);
    setError('');

    void getHelpArticle(slug)
      .then((data) => {
        if (!cancelled) setArticle(data);
      })
      .catch((err) => {
        if (!cancelled) {
          setArticle(null);
          setError(err?.message || t('help.panel.load_failed'));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [open, slug]);

  const html = useMemo(
    () => renderHelpMarkdown(article?.content || ''),
    [article?.content],
  );

  useEffect(() => {
    if (!open || !anchor || loading || !bodyRef.current) return;
    const root = bodyRef.current;
    const timer = window.setTimeout(() => {
      const target = root.querySelector(`#${CSS.escape(anchor)}`);
      target?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [open, anchor, loading, html]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === 'Escape') onClose?.();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, onClose]);

  if (!open) return null;

  const title = article?.title || label || slug;

  return (
    <div className="help-panel-root">
      <button
        type="button"
        className="help-panel-scrim"
        aria-label={t('help.panel.close')}
        onClick={onClose}
      />
      <aside className="help-panel" role="dialog" aria-modal="true" aria-label={title}>
        <header className="help-panel__header">
          <div className="help-panel__title-wrap">
            <span className="material-symbols-outlined help-panel__icon" aria-hidden="true">
              {helpArticleIcon(slug)}
            </span>
            <div className="help-panel__titles">
              {label ? <p className="help-panel__kicker">{label}</p> : null}
              <h2 className="help-panel__title">{title}</h2>
            </div>
          </div>
          <CoreUIButton
            type="button"
            variant="icon"
            size="icon"
            className="help-panel__close"
            aria-label={t('help.panel.close')}
            onClick={onClose}
          >
            <span className="material-symbols-outlined" aria-hidden="true">
              close
            </span>
          </CoreUIButton>
        </header>

        <div className="help-panel__actions">
          <CoreUIButton
            type="button"
            variant="ghost"
            onClick={() => {
              onOpenFullHelp?.(slug, anchor);
              onClose?.();
            }}
          >
            <span className="material-symbols-outlined coreui-icon--sm" aria-hidden="true">
              menu_book
            </span>
            {t('help.panel.open_full')}
          </CoreUIButton>
        </div>

        <div ref={bodyRef} className="help-panel__body">
          {error ? (
            <ActionableError message={error} onRetry={() => {
              setError('');
              setLoading(true);
              void getHelpArticle(slug)
                .then(setArticle)
                .catch((err) => setError(err?.message || t('help.panel.load_failed')))
                .finally(() => setLoading(false));
            }}
            />
          ) : null}
          {loading ? (
            <div className="help-panel__loading" aria-busy="true">
              <M3LoadingIndicator size="md" />
            </div>
          ) : article ? (
            <div
              className="markdown-prose markdown-prose--preview help-article-body help-panel__article"
              dangerouslySetInnerHTML={{ __html: html }}
            />
          ) : null}
        </div>
      </aside>
    </div>
  );
}
