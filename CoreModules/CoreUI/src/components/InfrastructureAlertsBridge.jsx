import { useEffect, useRef } from 'react';
import { getRagStatus } from '../services/api';
import { useNotificationCenter } from './NotificationCenterContext';

const RAG_UNAVAILABLE_AGGREGATION_KEY = 'infrastructure:rag-unavailable';

function clampPollSec(raw) {
  const n = parseInt(String(raw ?? ''), 10);
  if (Number.isNaN(n)) return 5;
  return Math.min(300, Math.max(2, n));
}

/** Stable key for deduping the same infrastructure failure across polls. */
function ragFailureKey(rag) {
  if (!rag || rag.running) return null;
  const url = String(rag.url ?? '').trim() || '—';
  const err = rag.error != null ? String(rag.error) : '';
  const http = rag.http_status != null ? String(rag.http_status) : '';
  return `rag|${url}|h:${http}|e:${err.slice(0, 400)}`;
}

/**
 * Persists Qdrant/RAG reachability failures (same source as /rag/status server log) into
 * the notification center, with deduplication until Qdrant responds again.
 */
export default function InfrastructureAlertsBridge({ pollIntervalSec = 5 }) {
  const { sessionId, persistNotification } = useNotificationCenter();
  const lastRagKeyRef = useRef(null);

  useEffect(() => {
    if (!sessionId) return undefined;

    const sec = clampPollSec(pollIntervalSec);

    const tick = async () => {
      let rag;
      try {
        rag = await getRagStatus();
      } catch (e) {
        rag = {
          running: false,
          url: null,
          error: e?.message || String(e),
        };
      }

      if (rag.running) {
        lastRagKeyRef.current = null;
      } else {
        const key = ragFailureKey(rag);
        if (key && key !== lastRagKeyRef.current) {
          lastRagKeyRef.current = key;
          const baseUrl = rag.url || 'Qdrant URL unknown';
          const detail =
            rag.error != null && String(rag.error).trim() !== ''
              ? String(rag.error)
              : rag.http_status != null
                ? `GET /collections → HTTP ${rag.http_status}`
                : 'Qdrant did not respond';
          try {
            await persistNotification({
              kind: 'error',
              source: 'rag',
              title: 'Qdrant / RAG unavailable',
              aggregation_key: RAG_UNAVAILABLE_AGGREGATION_KEY,
              message: `${detail} · ${baseUrl}`.slice(0, 800),
            });
          } catch (err) {
            console.error('InfrastructureAlertsBridge: persist (rag) failed', err);
          }
        }
      }
    };

    void tick();
    const id = setInterval(() => void tick(), sec * 1000);
    return () => clearInterval(id);
  }, [sessionId, pollIntervalSec, persistNotification]);

  return null;
}
