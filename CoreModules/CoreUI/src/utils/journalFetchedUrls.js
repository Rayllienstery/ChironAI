function asObject(value) {
  return value && typeof value === 'object' && !Array.isArray(value) ? value : {};
}

function uniqueUrls(raw) {
  if (!Array.isArray(raw) || raw.length === 0) return [];
  const seen = new Set();
  const urls = [];
  for (const item of raw) {
    const url = String(item || '').trim();
    if (!url) continue;
    const key = url.replace(/\/+$/, '').toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    urls.push(url);
  }
  return urls;
}

export function journalFetchedUrls(meta) {
  const data = asObject(meta);
  const trace = asObject(data.trace);
  const request = asObject(data.request || trace.request);
  const internet = asObject(data.internet || trace.internet);
  const buckets = [data.url_fetch_urls, request.url_fetch_urls, internet.url_fetch_urls];
  for (const raw of buckets) {
    const urls = uniqueUrls(raw);
    if (urls.length) return urls;
  }
  return [];
}

export function journalFetchedUrlCount(meta) {
  const data = asObject(meta);
  const trace = asObject(data.trace);
  const request = asObject(data.request || trace.request);
  const internet = asObject(data.internet || trace.internet);
  const urls = journalFetchedUrls(data);
  const raw = data.url_fetch_count ?? request.url_fetch_count ?? internet.url_fetch_count;
  const parsed = Number(raw);
  if (Number.isFinite(parsed) && parsed > 0) {
    return Math.max(parsed, urls.length);
  }
  return urls.length;
}
