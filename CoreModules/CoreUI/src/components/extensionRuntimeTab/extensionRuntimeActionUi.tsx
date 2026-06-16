import { formatElapsedMs } from '../../utils/elapsedTime';
import type { ActiveAction } from './reportActionOutcome';

type ActionElapsedChipProps = {
  action: ActiveAction | null;
  nowMs: number;
};

export function ExtensionActionLiveNotification({
  action,
  nowMs,
}: ActionElapsedChipProps) {
  if (!action) return null;
  const elapsedMs = Math.max(0, nowMs - action.startedAt);
  return (
    <div className="extensions-runtime-action-live">
      <div className="extensions-runtime-action-live__row">
        <span className="extensions-runtime-action-live__label">Action</span>
        <span className="extensions-runtime-action-live__value">{action.label}</span>
      </div>
      <div className="extensions-runtime-action-live__row">
        <span className="extensions-runtime-action-live__label">Elapsed</span>
        <span className="extensions-runtime-action-live__timer">{formatElapsedMs(elapsedMs)}</span>
      </div>
    </div>
  );
}

export function ActionElapsedChip({ action, nowMs }: ActionElapsedChipProps) {
  if (!action) return null;
  return (
    <span className="extensions-runtime-action-timer" aria-label={`Elapsed ${formatElapsedMs(nowMs - action.startedAt)}`}>
      <span className="material-symbols-outlined" aria-hidden="true">timer</span>
      {formatElapsedMs(nowMs - action.startedAt)}
    </span>
  );
}
