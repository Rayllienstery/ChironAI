export function extractFieldDefaults(schema: unknown): Record<string, string> {
  const next: Record<string, string> = {};
  const pages = Array.isArray((schema as { pages?: unknown })?.pages)
    ? (schema as { pages: unknown[] }).pages
    : [];
  pages.forEach((page) => {
    const sections = Array.isArray((page as { sections?: unknown })?.sections)
      ? (page as { sections: unknown[] }).sections
      : [];
    sections.forEach((section) => {
      const components = Array.isArray((section as { components?: unknown })?.components)
        ? (section as { components: unknown[] }).components
        : [];
      components.forEach((component) => {
        const c = component as { key?: string; type?: string; value?: string };
        if (!c?.key) return;
        if (c.type === 'input' || c.type === 'select') {
          next[c.key] = c.value ?? '';
        }
      });
    });
  });
  return next;
}

export function extractContentFieldDefaults(content: unknown): Record<string, string> {
  const next: Record<string, string> = {};
  const fields = Array.isArray((content as { fields?: unknown })?.fields)
    ? (content as { fields: unknown[] }).fields
    : [];
  fields.forEach((field) => {
    const f = field as { key?: string; value?: string };
    if (!f?.key) return;
    next[f.key] = f.value ?? '';
  });
  return next;
}

export function isRuntimeModelDetailsForModal(details: unknown): boolean {
  if (!details || typeof details !== 'object' || Array.isArray(details)) return false;
  const d = details as Record<string, unknown>;
  return Boolean(
    String(d.id ?? d.model ?? d.name ?? '').trim()
    || d.details
    || d.model_info
    || d.capabilities
    || d.modelfile,
  );
}

export function normalizeModelDetailsForModal(
  details: unknown,
  modelId = '',
): Record<string, unknown> {
  const src = details && typeof details === 'object' && !Array.isArray(details)
    ? details as Record<string, unknown>
    : {};
  const id = String(src.id ?? src.model ?? src.name ?? modelId ?? '').trim();
  return {
    ...src,
    id: String(src.id ?? id).trim(),
    model: String(src.model ?? id).trim(),
  };
}

export function collectSchemaComponents(schema: unknown): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [];
  const pages = Array.isArray((schema as { pages?: unknown })?.pages)
    ? (schema as { pages: unknown[] }).pages
    : [];
  pages.forEach((page) => {
    const sections = Array.isArray((page as { sections?: unknown })?.sections)
      ? (page as { sections: unknown[] }).sections
      : [];
    sections.forEach((section) => {
      const components = Array.isArray((section as { components?: unknown })?.components)
        ? (section as { components: unknown[] }).components
        : [];
      components.forEach((c) => out.push(c as Record<string, unknown>));
    });
  });
  return out;
}

export function serviceActionIcon(actionId: string): string {
  switch (String(actionId || '')) {
    case 'refresh':
      return 'refresh';
    case 'start':
    case 'start_service':
      return 'play_arrow';
    case 'stop':
    case 'stop_service':
      return 'stop';
    case 'clear_backend':
      return 'backspace';
    case 'open_external':
      return 'open_in_new';
    default:
      return '';
  }
}

export function formatBytesLoose(value: unknown): string {
  const raw = String(value ?? '').trim();
  if (!raw) return '';
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return raw;
  const gb = n / 1024 ** 3;
  if (gb >= 1) return `${gb.toFixed(2)} GB`;
  const mb = n / 1024 ** 2;
  if (mb >= 1) return `${mb.toFixed(1)} MB`;
  const kb = n / 1024;
  if (kb >= 1) return `${kb.toFixed(0)} KB`;
  return `${n} B`;
}

export function formatIsoShort(value: unknown): string {
  const raw = String(value ?? '').trim();
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return raw;
  return d.toLocaleString();
}

export function parseModelName(raw: unknown): { displayName: string; quantization: string } {
  const s = String(raw ?? '').trim();
  if (!s) return { displayName: s, quantization: '' };
  const lastPart = s.includes('/') ? s.split('/').pop()! : s;
  const parts = lastPart.split(':');
  const quantization = parts.length > 1 ? parts.pop()! : '';
  let displayName = parts.join(':');
  displayName = displayName.replace(/-GGUF$/i, '');
  return { displayName, quantization };
}

export function isRuntimeStillLoadingMessage(message: unknown): boolean {
  return String(message || '').toLowerCase().includes('extension runtime is still loading');
}

function extensionTabLoadStatus(payload: unknown): string {
  const loadState = (payload as { load_state?: { status?: string } })?.load_state;
  return String(loadState?.status || '').trim().toLowerCase();
}

export function isExtensionTabWaiting(payload: unknown): boolean {
  return ['missing', 'refreshing', 'stale', 'timeout'].includes(extensionTabLoadStatus(payload));
}

export function isExtensionTabTerminalError(payload: unknown): boolean {
  return ['failed'].includes(extensionTabLoadStatus(payload));
}

export function hasRenderableExtensionPayload(payload: unknown): boolean {
  const contentType = String((payload as { content?: { type?: string } })?.content?.type || '').trim();
  if (contentType) return true;
  const pages = (payload as { schema?: { pages?: unknown[] } })?.schema?.pages;
  return Array.isArray(pages) && pages.length > 0;
}

export function modelIsHidden(row: Record<string, unknown>): boolean {
  const hiddenRaw = String(row?.hidden ?? '').trim().toLowerCase();
  return hiddenRaw === 'yes' || hiddenRaw === 'true' || hiddenRaw === '1';
}
