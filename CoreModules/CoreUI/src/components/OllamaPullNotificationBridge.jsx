import { useEffect, useRef, useState } from 'react';
import { useNotificationCenter } from './NotificationCenterContext';
import { ollamaPullProgressText, subscribeOllamaPullJob } from './ollamaPullJobStore';

function PullJobView({ job, onOpenOllama }) {
  const progress = job?.progress || {};
  const pct = progress.percent;
  const failed = Boolean(job?.error || progress.error);
  const progressText = ollamaPullProgressText(progress);
  return (
    <div className={`notification-ollama-pull${failed ? ' notification-ollama-pull--error' : ''}`}>
      <div className="notification-ollama-pull__header">
        <span
          className={job?.running ? 'notification-ollama-pull__spinner' : 'material-symbols-outlined'}
          aria-hidden="true"
        >
          {job?.running ? '' : failed ? 'error' : 'check_circle'}
        </span>
        <div>
          <strong>{progress.model || job?.model || 'Ollama model'}</strong>
          <span>{failed ? (progress.error || job?.error) : progressText}</span>
        </div>
        {pct != null ? <b>{pct}%</b> : null}
      </div>
      <div className="notification-ollama-pull__bar" aria-hidden="true">
        <span style={{ width: pct != null ? `${pct}%` : '38%' }} />
      </div>
      <div className="notification-ollama-pull__actions">
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
    const failed = Boolean(job.error || job.progress?.error);
    persistNotification({
      kind: failed ? 'error' : 'event',
      source: 'ollama',
      title: failed ? 'Model pull failed' : 'Model pull finished',
      message: failed
        ? String(job.error || job.progress?.error || '').slice(0, 400)
        : `${job.model} is ready.`,
      metadata: {
        model: job.model,
      },
    });
  }, [job, persistNotification]);

  return null;
}
