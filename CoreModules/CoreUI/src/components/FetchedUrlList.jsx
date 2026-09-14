import Card from './Card';
import { journalFetchedUrlCount, journalFetchedUrls } from '../utils/journalFetchedUrls';

function FetchedUrlItems({ meta }) {
  const urls = journalFetchedUrls(meta);
  const count = journalFetchedUrlCount(meta);
  const hidden = Math.max(0, count - urls.length);
  if (urls.length === 0) {
    return <p className="coreui-text-muted-sm" style={{ margin: 0 }}>No web URLs this turn.</p>;
  }
  return (
    <>
      <ol className="coreui-list-tight">
        {urls.map((url) => (
          <li key={url}>
            <a
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="coreui-text-break-all"
            >
              {url}
            </a>
          </li>
        ))}
      </ol>
      {hidden > 0 ? (
        <p className="coreui-text-muted-sm" style={{ margin: 0 }}>
          +{hidden} more not listed
        </p>
      ) : null}
    </>
  );
}

export function JournalFetchedUrlList({ meta }) {
  const count = journalFetchedUrlCount(meta);
  return (
    <Card className="coreui-p-md coreui-stack-xs" aria-label="Fetched URLs">
      <strong>Fetched URLs{count ? ` (${count})` : ''}</strong>
      <FetchedUrlItems meta={meta} />
    </Card>
  );
}

export function ProxyLogFetchedUrls({ metadata }) {
  const count = journalFetchedUrlCount(metadata);
  return (
    <div className="proxy-log-section" aria-label="Fetched URLs">
      <strong>Fetched URLs{count ? ` (${count})` : ''}</strong>
      <FetchedUrlItems meta={metadata} />
    </div>
  );
}
