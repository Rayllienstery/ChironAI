import type { FieldState } from './comparePayload';

export type PayloadKeyOverrides = Record<string, string>;

export function buildActionPayload(
  payloadKeys: unknown,
  fieldState: FieldState,
  overrides: PayloadKeyOverrides = {},
): Record<string, string> {
  const body: Record<string, string> = {};
  const keys = Array.isArray(payloadKeys) ? payloadKeys : [];
  keys.forEach((key) => {
    if (typeof key !== 'string' || !key.trim()) return;
    if (Object.prototype.hasOwnProperty.call(overrides, key)) {
      body[key] = overrides[key];
      return;
    }
    body[key] = fieldState[key] ?? '';
  });
  return body;
}

export function actionLabel(
  action: { label?: string; title?: string } | null | undefined,
  actionId: string,
): string {
  return String(action?.label || action?.title || actionId || 'Action').trim();
}

export function serviceActionTimeoutMs(actionId: string): number {
  return actionId === 'start_service' || actionId === 'stop_service' ? 30 * 60 * 1000 : 30_000;
}
