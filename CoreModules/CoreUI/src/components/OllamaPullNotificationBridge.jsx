import { useEffect, useRef, useState } from 'react';
import { useNotificationCenter } from './NotificationCenterContext';
import {
  cancelOllamaPullJob,
  ollamaPullProgressText,
  ollamaPullRateText,
  subscribeOllamaPullJob,
} from './ollamaPullJobStore';

function PullJobView({ job, onOpenOllama }) {
  const progress = job?.progress || {};
  const pct = progress.percent;
  const cancelled = Boolean(progress.cancelled);
  const failed = Boolean(!cancelled && (job?.error || progress.error));
  const progressText = ollamaPullProgressText(progress);
  const rateText = job?.running && !failed && !cancelled ? ollamaPullRateText(progress) : '';
  const tone = failed ? 'error' : cancelled ? 'cancelled' : '';
  return (
    <div className={`notification-ollama-pull${tone ? ` notification-ollama-pull--${tone}` : ''}`}>
      <div className="notification-ollama-pull__header">
        <span
          className={job?.running ? 'notification-ollama-pull__spinner' : 'material-symbols-outlined'}
          aria-hidden="true"
        >
          {job?.running ? '' : failed ? 'error' : cancelled ? 'block' : 'check_circle'}
        </span>
        <div>
          <strong>{progress.model || job?.model || 'Ollama model'}</strong>
          <span>{failed ? (progress.error || job?.error) : progressText}</span>
          {rateText ? <span className="notification-ollama-pull__rate">{rateText}</span> : null}
        </div>
        {pct != null ? <b>{pct}%</b> : null}
      </div>
      <div className="notification-ollama-pull__bar" aria-hidden="true">
        <span style={{ width: pct != null ? `${pct}%` : '38%' }} />
      </div>
      <div className="notification-ollama-pull__actions">
        {job?.running ? (
          <button type="button" className="notification-ollama-pull__cancel" onClick={cancelOllamaPullJob}>
            Cancel download
          </button>
        ) : null}
        <button type="button" onClick={onOpenOllama}>Open Ollama</button>
      </div>
    </div>
  );
}

export default function OllamaPullNotificationBridge({ onOpenOllama }) {
  const [job, setJob] = useState(null);
  const {
    setLiveActivity,
    clearLiveActivity,
    clearLiveSuppression,
    persistNotification,
  } = useNotificationCenter();
  const prevRunningRef = useRef(false);
  const persistedKeyRef = useRef('');

  useEffect(() => subscribeOllamaPullJob(setJob), []);

  useEffect(() => {
    const active = Boolean(job?.running);
    if (active) {
      clearLiveSuppression('ollama-pull-model');
      setLiveActivity(
        'ollama-pull-model',
        'ollama',
        <PullJobView job={job} onOpenOllama={onOpenOllama} />,
      );
    } else {
      clearLiveActivity('ollama-pull-model');
    }
  }, [job, onOpenOllama, setLiveActivity, clearLiveActivity, clearLiveSuppression]);

  useEffect(() => {
    const wasRunning = prevRunningRef.current;
    const running = Boolean(job?.running);
    prevRunningRef.current = running;
    if (!wasRunning || running || !job?.finishedAt) return;

    const key = `${job.model}:${job.finishedAt}`;
    if (persistedKeyRef.current === key) return;
    persistedKeyRef.current = key;
    const cancelled = Boolean(job.progress?.cancelled);
    const failed = Boolean(!cancelled && (job.error || job.progress?.error));
    persistNotification({
      kind: failed ? 'error' : 'event',
      source: 'ollama',
      title: cancelled ? 'Model pull cancelled' : failed ? 'Model pull failed' : 'Model pull finished',
      message: cancelled
        ? `Stopped downloading ${job.model}.`
        : failed
          ? String(job.error || job.progress?.error || '').slice(0, 400)
          : `${job.model} is ready.`,
      metadata: {
        model: job.model,
      },
    });
  }, [job, persistNotification]);

  return null;
}
