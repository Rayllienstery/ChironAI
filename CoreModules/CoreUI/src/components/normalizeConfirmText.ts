const MAX_CONFIRM_LENGTH = 500;

/** Normalize extension-supplied confirm copy for safe plain-text display. */
export function normalizeConfirmText(raw: unknown): string {
  const trimmed = String(raw ?? '').trim();
  if (!trimmed) return '';
  const stripped = trimmed.replace(/[\x00-\x1f\x7f]/g, '');
  if (stripped.length <= MAX_CONFIRM_LENGTH) return stripped;
  return `${stripped.slice(0, MAX_CONFIRM_LENGTH)}…`;
}
