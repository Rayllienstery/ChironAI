/**
 * Parse `slug` or `slug#anchor` help references used by InfoButton and HelpPanel.
 */
export function parseHelpRef(ref) {
  const raw = String(ref || '').trim();
  if (!raw) return { slug: '', anchor: '' };
  const hashIndex = raw.indexOf('#');
  if (hashIndex === -1) {
    return { slug: raw.toLowerCase(), anchor: '' };
  }
  return {
    slug: raw.slice(0, hashIndex).trim().toLowerCase(),
    anchor: raw.slice(hashIndex + 1).trim().toLowerCase(),
  };
}
