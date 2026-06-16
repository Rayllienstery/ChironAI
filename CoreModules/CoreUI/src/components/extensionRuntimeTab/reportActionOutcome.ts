export type ActiveAction = {
  id: string;
  label: string;
  startedAt: number;
};

export type ActionOutcome = {
  ok: boolean;
  message: string;
  durationMs: number;
  startedAt: number;
  completedAt: number;
  [key: string]: unknown;
};

export function buildActionOutcome(
  action: ActiveAction,
  result: Record<string, unknown> | null | undefined,
  error: unknown = null,
): ActionOutcome {
  const completedAt = Date.now();
  const durationMs = Math.max(0, completedAt - action.startedAt);
  const ok = error ? false : result?.ok !== false;
  const message = error
    ? String((error as Error)?.message || error)
    : String(result?.message || 'Action completed');
  return {
    ...(result || {}),
    ok,
    message,
    durationMs,
    startedAt: action.startedAt,
    completedAt,
  };
}

export type ExtensionNotificationInput = {
  kind: 'event' | 'error';
  source: 'extensions';
  title: string;
  message: string;
  metadata: Record<string, unknown>;
  aggregation_key: string;
};

export function buildExtensionActionNotification(
  action: ActiveAction,
  extensionId: string,
  outcome: ActionOutcome,
): ExtensionNotificationInput {
  return {
    kind: outcome.ok ? 'event' : 'error',
    source: 'extensions',
    title: `${action.label} ${outcome.ok ? 'completed' : 'failed'}`,
    message: outcome.message,
    metadata: {
      extension_id: extensionId,
      action_id: action.id,
      started_at: new Date(action.startedAt).toISOString(),
      completed_at: new Date(outcome.completedAt).toISOString(),
      duration_ms: outcome.durationMs,
    },
    aggregation_key: `extension-action:${extensionId}:${action.id}:${outcome.completedAt}`,
  };
}

export function buildSimpleActionOutcome(error: unknown): { ok: false; message: string } {
  return { ok: false, message: String((error as Error)?.message || error) };
}
