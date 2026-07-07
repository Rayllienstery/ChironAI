import React, { useEffect, useRef, useState } from "react";
import Card from "../Card";
import { t } from "../../services/i18n.js";
import {
  addCrawlerSource,
  crawlSource,
  getCrawlerSource,
  getCrawlerSourcePages,
  getCrawlerSources,
  getCrawlStatus,
  getRagCollections,
  updateCrawlerSource,
} from "../../services/api";

export function useCrawlerSection({ nc, activeSection }) {
  const [loading, setLoading] = useState(true);
  const [sources, setSources] = useState([]);
  const [selectedSource, setSelectedSource] = useState(null);
  const [sourcePages, setSourcePages] = useState([]);
  const [collections, setCollections] = useState([]);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [crawlingSources, setCrawlingSources] = useState(new Set());
  const [crawlAllResults, setCrawlAllResults] = useState([]);
  const crawlPersistedCountRef = useRef(0);
  const [selectedSourceIds, setSelectedSourceIds] = useState(new Set());
  const [showAddSourceModal, setShowAddSourceModal] = useState(false);
  const [addSourceForm, setAddSourceForm] = useState({
    id: "",
    url: "",
    max_depth: 2,
    crawler: "playwright",
    doc_only: true,
    seed_urls: [],
  });
  const [addingSource, setAddingSource] = useState(false);
  const [showEditSourceModal, setShowEditSourceModal] = useState(false);
  const [editingSourceId, setEditingSourceId] = useState(null);
  const [editSourceForm, setEditSourceForm] = useState({
    id: "",
    url: "",
    max_depth: 2,
    crawler: "playwright",
    doc_only: true,
    seed_urls: [],
  });
  const [updatingSource, setUpdatingSource] = useState(false);

  const loadSources = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getCrawlerSources();
      const loaded = data.sources || [];
      setSources(loaded);
      // Keep selection only for sources that still exist
      setSelectedSourceIds((prev) => {
        if (!prev || prev.size === 0) return prev;
        const ids = new Set(loaded.map((s) => s.id));
        const next = new Set();
        prev.forEach((id) => {
          if (ids.has(id)) next.add(id);
        });
        return next;
      });
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadCollections = async () => {
    try {
      const data = await getRagCollections();
      setCollections(data.collections || []);
    } catch (e) {
      // Non-critical error
      console.warn("Failed to load collections:", e);
    }
  };

  useEffect(() => {
    loadSources();
    loadCollections();
  }, []);
  useEffect(() => {
    if (!nc?.persistNotification) return;
    const len = crawlAllResults.length;
    if (len === 0) {
      crawlPersistedCountRef.current = 0;
      return;
    }
    if (len <= crawlPersistedCountRef.current) return;
    const newRows = crawlAllResults.slice(crawlPersistedCountRef.current);
    crawlPersistedCountRef.current = len;
    for (const r of newRows) {
      const srcLabel =
        sources.find((s) => s.id === r.sourceId)?.id || r.sourceId;
      nc.persistNotification({
        kind: r.success ? "event" : "error",
        source: "crawler",
        title: r.success ? "Crawl finished" : "Crawl failed",
        message: r.success
          ? `Source: ${srcLabel}`
          : `${srcLabel}: ${String(
              r.error || `exit ${r.returnCode ?? "?"}`,
            ).slice(0, 400)}`,
      });
    }
  }, [crawlAllResults, nc, sources]);

  useEffect(() => {
    if (
      !nc ||
      activeSection !== "crawler" ||
      crawlingSources.size === 0
    ) {
      nc?.clearLiveActivity?.("crawler-progress");
      return undefined;
    }
    nc.clearLiveSuppression?.("crawler-progress");
    nc.setLiveActivity(
      "crawler-progress",
      "crawler",
      <Card className="crawler-progress-panel" role="status" aria-live="polite">
        <div className="crawler-progress-header">
          <span className="crawler-progress-spinner" aria-hidden="true" />
          <span className="crawler-progress-title">{t("crawler.sources.crawling")}</span>
          <span className="crawler-progress-sources">
            {Array.from(crawlingSources).join(", ")}
          </span>
        </div>
      </Card>,
    );
    return () => nc.clearLiveActivity("crawler-progress");
  }, [nc, activeSection, crawlingSources]);

  // Poll crawl status for sources that are crawling
  useEffect(() => {
    if (crawlingSources.size === 0) return;

    const interval = setInterval(async () => {
      const statusChecks = Array.from(crawlingSources).map(async (sourceId) => {
        try {
          const status = await getCrawlStatus(sourceId);
          if (status.status === "finished" || status.status === "not_running") {
            const returnCode = status.return_code;
            const success =
              status.status === "finished" ? returnCode === 0 : true;
            const errorDetail = (status.stderr && status.stderr.trim()) || null;
            setCrawlAllResults((prev) => [
              ...prev,
              {
                sourceId,
                success,
                returnCode: returnCode ?? undefined,
                error: errorDetail,
              },
            ]);
            setCrawlingSources((prev) => {
              const next = new Set(prev);
              next.delete(sourceId);
              return next;
            });
            loadSources();
            if (selectedSource === sourceId) {
              try {
                const data = await getCrawlerSourcePages(sourceId);
                setSourcePages(data.pages || []);
              } catch (e) {
                console.error(`Failed to reload pages for ${sourceId}:`, e);
              }
            }
          }
        } catch (e) {
          console.error(`Failed to check crawl status for ${sourceId}:`, e);
        }
      });
      await Promise.all(statusChecks);
    }, 2000);

    return () => clearInterval(interval);
  }, [crawlingSources, selectedSource]);
  const handleSourceClick = async (sourceId) => {
    if (selectedSource === sourceId) {
      setSelectedSource(null);
      setSourcePages([]);
      return;
    }
    setSelectedSource(sourceId);
    setError(null);
    try {
      const data = await getCrawlerSourcePages(sourceId);
      setSourcePages(data.pages || []);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleRefresh = () => {
    loadSources();
    loadCollections();
    if (selectedSource) {
      handleSourceClick(selectedSource);
    }
  };
  const toggleSourceSelected = (sourceId) => {
    setSelectedSourceIds((prev) => {
      const next = new Set(prev);
      if (next.has(sourceId)) {
        next.delete(sourceId);
      } else {
        next.add(sourceId);
      }
      return next;
    });
  };

  const handleToggleSelectAll = () => {
    setSelectedSourceIds((prev) => {
      if (!sources.length) return new Set();
      const allSelected = sources.every((s) => prev.has(s.id));
      if (allSelected) {
        return new Set();
      }
      return new Set(sources.map((s) => s.id));
    });
  };

  const handleCrawlSource = async (sourceId) => {
    if (crawlingSources.has(sourceId)) return;
    setCrawlAllResults([]);
    setCrawlingSources((prev) => new Set(prev).add(sourceId));
    setError(null);
    try {
      await crawlSource(sourceId);
    } catch (e) {
      setError(e.message);
      setCrawlAllResults((prev) => [
        ...prev,
        { sourceId, success: false, returnCode: undefined, error: e.message },
      ]);
      setCrawlingSources((prev) => {
        const next = new Set(prev);
        next.delete(sourceId);
        return next;
      });
    }
  };

  const handleCrawlAll = async () => {
    if (sources.length === 0 || crawlingSources.size > 0) return;
    setCrawlAllResults([]);
    setError(null);
    const ids = sources.map((s) => s.id);
    setCrawlingSources((prev) => new Set([...prev, ...ids]));
    for (const sourceId of ids) {
      try {
        await crawlSource(sourceId);
      } catch (e) {
        setError(e.message);
        setCrawlAllResults((prev) => [
          ...prev,
          { sourceId, success: false, returnCode: undefined, error: e.message },
        ]);
        setCrawlingSources((prev) => {
          const next = new Set(prev);
          next.delete(sourceId);
          return next;
        });
      }
    }
  };

  const handleCrawlSelected = () => {
    if (busy || crawlingSources.size > 0 || selectedSourceIds.size === 0)
      return;
    const ids = sources
      .filter((s) => selectedSourceIds.has(s.id))
      .map((s) => s.id);
    if (!ids.length) return;
    ids.forEach((id) => {
      handleCrawlSource(id);
    });
  };

  const handleAddSource = async () => {
    if (!addSourceForm.id.trim() || !addSourceForm.url.trim()) {
      setError("Source ID and URL are required");
      return;
    }

    // Filter out empty seed URLs
    const seedUrls = addSourceForm.seed_urls.filter((url) => url && url.trim());

    setAddingSource(true);
    setError(null);
    try {
      await addCrawlerSource({
        ...addSourceForm,
        seed_urls: seedUrls,
      });
      setShowAddSourceModal(false);
      setAddSourceForm({
        id: "",
        url: "",
        max_depth: 2,
        crawler: "playwright",
        doc_only: true,
        seed_urls: [],
      });
      await loadSources();
      alert("Source added successfully!");
    } catch (e) {
      setError(e.message);
    } finally {
      setAddingSource(false);
    }
  };

  const handleEditSource = async (sourceId) => {
    setEditingSourceId(sourceId);
    setError(null);
    try {
      const sourceData = await getCrawlerSource(sourceId);
      setEditSourceForm({
        id: sourceData.id,
        url: sourceData.url || "",
        max_depth: sourceData.max_depth || 2,
        crawler: sourceData.crawler || "playwright",
        doc_only:
          sourceData.doc_only !== undefined ? sourceData.doc_only : true,
        seed_urls: sourceData.seed_urls || [],
      });
      setShowEditSourceModal(true);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleUpdateSource = async () => {
    if (!editSourceForm.url.trim()) {
      setError("URL is required");
      return;
    }

    // Filter out empty seed URLs
    const seedUrls = editSourceForm.seed_urls.filter(
      (url) => url && url.trim(),
    );

    setUpdatingSource(true);
    setError(null);
    try {
      await updateCrawlerSource(editingSourceId, {
        url: editSourceForm.url,
        max_depth: editSourceForm.max_depth,
        crawler: editSourceForm.crawler,
        doc_only: editSourceForm.doc_only,
        seed_urls: seedUrls,
      });
      setShowEditSourceModal(false);
      setEditingSourceId(null);
      await loadSources();
      alert("Source updated successfully!");
    } catch (e) {
      setError(e.message);
    } finally {
      setUpdatingSource(false);
    }
  };

  return {
    loading,
    sources,
    selectedSource,
    sourcePages,
    collections,
    error,
    setError,
    busy,
    crawlingSources,
    crawlAllResults,
    setCrawlAllResults,
    selectedSourceIds,
    showAddSourceModal,
    setShowAddSourceModal,
    addSourceForm,
    setAddSourceForm,
    addingSource,
    showEditSourceModal,
    setShowEditSourceModal,
    editingSourceId,
    editSourceForm,
    setEditSourceForm,
    updatingSource,
    loadSources,
    loadCollections,
    handleSourceClick,
    handleRefresh,
    toggleSourceSelected,
    handleToggleSelectAll,
    handleCrawlSource,
    handleCrawlAll,
    handleCrawlSelected,
    handleAddSource,
    handleEditSource,
    handleUpdateSource,
  };
}
