import { useEffect, useRef } from 'react';
import { RagTestRunPanelBody } from './RagTestRunPanel';
import { useNotificationCenter } from './NotificationCenterContext';

/**
 * Registers RAG test run as a live notification and persists a history row when the run ends.
 */
export default function RagTestRunNotificationBridge({
  ragTestRunning,
  ragTestRunJobId,
  ragTestRunProgress,
  ragTestRunError,
  onCancel,
  onGoToRagTests,
}) {
  const {
    setLiveActivity,
    clearLiveActivity,
    clearLiveSuppression,
    persistNotification,
    sessionId,
  } = useNotificationCenter();
  const lastProgressRef = useRef(null);
  const lastJobIdRef = useRef(null);
  const prevActiveRef = useRef(false);

  useEffect(() => {
    if (ragTestRunProgress) {
      lastProgressRef.current = ragTestRunProgress;
    }
  }, [ragTestRunProgress]);

  useEffect(() => {
    if (ragTestRunJobId) {
      lastJobIdRef.current = ragTestRunJobId;
    }
  }, [ragTestRunJobId]);

  useEffect(() => {
    const active = !!(ragTestRunning || ragTestRunJobId);
    if (active) {
      clearLiveSuppression('rag-tests-run');
      setLiveActivity(
        'rag-tests-run',
        'rag-tests',
        <div className="rag-test-run-panel rag-test-run-panel-embed">
          <RagTestRunPanelBody
            running={ragTestRunning}
            runProgress={ragTestRunProgress}
            runError={ragTestRunError}
            onCancel={onCancel}
            onGoToRagTests={onGoToRagTests}
          />
        </div>,
      );
    } else {
      clearLiveActivity('rag-tests-run');
    }
    return () => clearLiveActivity('rag-tests-run');
  }, [
    ragTestRunning,
    ragTestRunJobId,
    ragTestRunProgress,
    ragTestRunError,
    onCancel,
    onGoToRagTests,
    setLiveActivity,
    clearLiveActivity,
    clearLiveSuppression,
  ]);

  useEffect(() => {
    const active = !!(ragTestRunning || ragTestRunJobId);
    const wasActive = prevActiveRef.current;
    prevActiveRef.current = active;
    if (!sessionId || !wasActive || active) {
      return;
    }
    const p = lastProgressRef.current || {};
    const err = ragTestRunError;
    persistNotification({
      kind: err ? 'error' : 'event',
      source: 'rag-tests',
      title: err ? 'RAG tests run failed' : 'RAG tests run finished',
      message: err
        ? String(err).slice(0, 400)
        : `${p.passed ?? 0} passed, ${p.failed ?? 0} failed`,
      metadata: {
        run_id: lastJobIdRef.current || null,
        passed: p.passed ?? 0,
        failed: p.failed ?? 0,
        total: p.total ?? 0,
      },
    });
  }, [
    ragTestRunning,
    ragTestRunJobId,
    sessionId,
    ragTestRunError,
    persistNotification,
  ]);

  return null;
}
