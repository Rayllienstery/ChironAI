import { useCallback, useEffect, useMemo, useState } from 'react';
import { getPipelinePreview, getRagModelSettings } from '../services/api';

export function mergePipelineSnapshot(snapshot, hybrid_sparse_enabled, rerank_for_rag) {
  if (!snapshot) return null;
  return {
    ...snapshot,
    hybrid_sparse_enabled,
    rerank_for_rag,
  };
}

/**
 * @param {{ liveHybridSparse?: boolean, liveRerankForRag?: boolean }} [opts]
 * When both live booleans are provided, merged uses them (RAG tab — reflects draft toggles).
 * Otherwise loads hybrid/rerank from getRagModelSettings after each reload (dashboard).
 */
export function useMergedPipelinePreview(opts = {}) {
  const { liveHybridSparse, liveRerankForRag } = opts;
  const useLiveRag =
    typeof liveHybridSparse === 'boolean' && typeof liveRerankForRag === 'boolean';

  const [snapshot, setSnapshot] = useState(null);
  const [serverHybrid, setServerHybrid] = useState(true);
  const [serverRerank, setServerRerank] = useState(false);

  const reload = useCallback(async () => {
    try {
      const p = await getPipelinePreview();
      setSnapshot(p);
      if (!useLiveRag) {
        const r = await getRagModelSettings();
        setServerHybrid(r?.hybrid_sparse_enabled !== false);
        setServerRerank(Boolean(r?.rerank_for_rag));
      }
    } catch (e) {
      console.error('Failed to load pipeline preview', e);
    }
  }, [useLiveRag]);

  useEffect(() => {
    reload();
  }, [reload]);

  const merged = useMemo(() => {
    if (useLiveRag) {
      return mergePipelineSnapshot(snapshot, liveHybridSparse, liveRerankForRag);
    }
    return mergePipelineSnapshot(snapshot, serverHybrid, serverRerank);
  }, [snapshot, useLiveRag, liveHybridSparse, liveRerankForRag, serverHybrid, serverRerank]);

  return { merged, reload, snapshot };
}
