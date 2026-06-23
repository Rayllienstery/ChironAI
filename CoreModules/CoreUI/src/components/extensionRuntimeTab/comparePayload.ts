/** Lightweight equality for extension tab polling without JSON.stringify. */

export type ExtensionTabPayload = Record<string, unknown> | null | undefined;

export type FieldState = Record<string, string>;

function loadStateFingerprint(loadState: unknown): string {
  if (!loadState || typeof loadState !== 'object') return '';
  const ls = loadState as Record<string, unknown>;
  const phases = ls.phases && typeof ls.phases === 'object' ? JSON.stringify(ls.phases) : '';
  return [
    String(ls.status ?? ''),
    String(ls.cached_at ?? ''),
    String(ls.finished_at ?? ''),
    String(ls.error ?? ''),
    String(ls.job_id ?? ''),
    phases,
  ].join('|');
}

function schemaFingerprint(schema: unknown): string {
  if (!schema || typeof schema !== 'object') return '';
  const pages = (schema as Record<string, unknown>).pages;
  if (!Array.isArray(pages)) return '';
  const parts: string[] = [];
  pages.forEach((page) => {
    if (!page || typeof page !== 'object') return;
    const sections = (page as Record<string, unknown>).sections;
    if (!Array.isArray(sections)) return;
    sections.forEach((section) => {
      if (!section || typeof section !== 'object') return;
      const components = (section as Record<string, unknown>).components;
      if (!Array.isArray(components)) return;
      components.forEach((component) => {
        if (!component || typeof component !== 'object') return;
        const c = component as Record<string, unknown>;
        parts.push(
          `${String(c.type ?? '')}:${String(c.key ?? c.action_id ?? '')}:${String(c.value ?? '')}:${String(c.status ?? '')}`,
        );
      });
    });
  });
  return parts.join(';');
}

function contentFingerprint(content: unknown): string {
  if (!content || typeof content !== 'object') return '';
  const c = content as Record<string, unknown>;
  const fields = Array.isArray(c.fields) ? c.fields : [];
  const fieldParts = fields.map((field) => {
    if (!field || typeof field !== 'object') return '';
    const f = field as Record<string, unknown>;
    return `${String(f.key ?? '')}=${String(f.value ?? '')}`;
  });
  return [
    String(c.type ?? ''),
    String(c.status ?? ''),
    String(c.message ?? ''),
    fieldParts.join(','),
  ].join('|');
}

export function extensionTabPayloadsEqual(
  prev: ExtensionTabPayload,
  next: ExtensionTabPayload,
): boolean {
  if (prev === next) return true;
  if (!prev || !next) return prev === next;

  if (loadStateFingerprint(prev.load_state) !== loadStateFingerprint(next.load_state)) {
    return false;
  }

  if (contentFingerprint(prev.content) !== contentFingerprint(next.content)) {
    return false;
  }

  if (schemaFingerprint(prev.schema) !== schemaFingerprint(next.schema)) {
    return false;
  }

  return true;
}

export function fieldStatesEqual(prev: FieldState, next: FieldState): boolean {
  const prevKeys = Object.keys(prev);
  const nextKeys = Object.keys(next);
  if (prevKeys.length !== nextKeys.length) return false;
  for (const key of prevKeys) {
    if (prev[key] !== next[key]) return false;
  }
  return true;
}
