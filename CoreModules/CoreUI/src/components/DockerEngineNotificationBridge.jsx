import { useCallback, useEffect, useRef, useState } from 'react';
import { getDockerStatus, startDockerEngine } from '../services/api';
import { useNotificationCenter } from './NotificationCenterContext';

const LIVE_ID = 'docker-engine-unavailable';
const START_WAIT_MS = 180_000;
const DOWN_POLL_MS = 2_000;

function DockerEngineNotice({ starting, error, onStart }) {
  const message = starting
    ? 'Starting Docker Desktop…'
    : (error || 'Docker Engine is not running. Start Docker to continue.');
  return (
    <>
      <div className="notification-center-card-message">{message}</div>
      <div className="notification-center-card-actions">
        {starting ? (
          <span
            className="notification-center-card-action-busy"
            role="status"
            aria-live="polite"
            aria-label="Starting Docker"
          >
            <span className="notification-center-card-spinner" aria-hidden="true" />
          </span>
        ) : (
          <button type="button" className="notification-center-card-action-btn" onClick={onStart}>
            Start Docker
          </button>
        )}
      </div>
    </>
  );
}

function clampPollSec(raw) {
  const n = parseInt(String(raw ?? ''), 10);
  if (Number.isNaN(n)) return 5;
  return Math.min(300, Math.max(2, n));
}

/**
 * Shows one live notification when Docker Engine is down, with a Start Docker
 * action that launches Docker Desktop and waits until the engine is ready.
 */
export default function DockerEngineNotificationBridge({ pollIntervalSec = 5 }) {
  const {
    sessionId,
    setLiveActivity,
    clearLiveActivity,
    clearLiveSuppression,
  } = useNotificationCenter();
  const [engineReady, setEngineReady] = useState(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState('');
  const startingRef = useRef(false);

  const onStart = useCallback(async () => {
    if (startingRef.current) return;
    startingRef.current = true;
    setStarting(true);
    setStartError('');
    try {
      const result = await startDockerEngine();
      if (result?.engine_ready) {
        setEngineReady(true);
      }
    } catch (e) {
      startingRef.current = false;
      setStarting(false);
      setStartError(e?.message || String(e) || 'Failed to start Docker');
    }
  }, []);

  useEffect(() => {
    startingRef.current = starting;
  }, [starting]);

  useEffect(() => {
    if (!starting) return undefined;
    const timeoutId = window.setTimeout(() => {
      startingRef.current = false;
      setStarting(false);
      setStartError((prev) => prev || 'Timed out waiting for Docker Engine. Try again.');
    }, START_WAIT_MS);
    return () => window.clearTimeout(timeoutId);
  }, [starting]);

  useEffect(() => {
    if (!sessionId) return undefined;

    const idleSec = clampPollSec(pollIntervalSec);
    let cancelled = false;
    let timerId = null;

    const schedule = (ready) => {
      window.clearTimeout(timerId);
      timerId = window.setTimeout(() => void tick(), ready ? idleSec * 1000 : DOWN_POLL_MS);
    };

    const tick = async () => {
      try {
        const status = await getDockerStatus();
        if (cancelled) return;
        setEngineReady(Boolean(status?.engine_ready));
        schedule(Boolean(status?.engine_ready));
      } catch {
        if (cancelled) return;
        schedule(false);
      }
    };

    void tick();
    return () => {
      cancelled = true;
      window.clearTimeout(timerId);
    };
  }, [sessionId, pollIntervalSec]);

  useEffect(() => {
    if (!sessionId || engineReady == null) return undefined;
    if (engineReady) {
      startingRef.current = false;
      setStarting(false);
      setStartError('');
      clearLiveActivity(LIVE_ID);
      clearLiveSuppression(LIVE_ID);
      return undefined;
    }
    setLiveActivity(
      LIVE_ID,
      'docker',
      <DockerEngineNotice starting={starting} error={startError} onStart={onStart} />,
      {
        title: starting ? 'Starting Docker' : 'Docker Engine unavailable',
        kind: 'error',
        sticky: true,
      },
    );
    return undefined;
  }, [
    sessionId,
    engineReady,
    starting,
    startError,
    onStart,
    setLiveActivity,
    clearLiveActivity,
    clearLiveSuppression,
  ]);

  useEffect(() => (
    () => clearLiveActivity(LIVE_ID)
  ), [clearLiveActivity]);

  return null;
}
