import { t } from "../services/i18n.js";

const INDEXING_PHASE_KEYS = {
  reading: "crawler.index_progress.phase.reading",
  prepare: "crawler.index_progress.phase.prepare",
  chunking: "crawler.index_progress.phase.chunking",
  embedding: "crawler.index_progress.phase.embedding",
  saving: "crawler.index_progress.phase.saving",
  cancelling: "crawler.index_progress.phase.cancelling",
  cancelled: "crawler.index_progress.phase.cancelled",
  idle: "",
  complete: "crawler.index_progress.phase.complete",
};

const SKIP_REASON_KEYS = {
  read_error: "crawler.index_progress.skip.read_error",
  too_short: "crawler.index_progress.skip.too_short",
  empty_after_prepare: "crawler.index_progress.skip.empty_after_prepare",
  filename_excluded: "crawler.index_progress.skip.filename_excluded",
  content_excluded: "crawler.index_progress.skip.content_excluded",
  chunk_failed: "crawler.index_progress.skip.chunk_failed",
  no_valid_chunks: "crawler.index_progress.skip.no_valid_chunks",
  embed_failed: "crawler.index_progress.skip.embed_failed",
  dim_mismatch: "crawler.index_progress.skip.dim_mismatch",
  other: "crawler.index_progress.skip.other",
};

function getPhaseLabel(phaseKey) {
  const messageKey = INDEXING_PHASE_KEYS[phaseKey];
  return messageKey ? t(messageKey) : phaseKey;
}

function getSkipReasonLabel(reason) {
  const messageKey = SKIP_REASON_KEYS[reason];
  return messageKey ? t(messageKey) : reason;
}

function formatIndexNumber(value) {
  const n = Number(value || 0);
  return Number.isFinite(n) ? new Intl.NumberFormat().format(n) : "0";
}

export function formatDurationMs(value) {
  const ms = Number(value || 0);
  const totalSeconds = Number.isFinite(ms) && ms > 0 ? Math.floor(ms / 1000) : 0;
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function issuePath(issue) {
  if (!issue || typeof issue !== "object") return "";
  return `${issue.source_id || ""}/${issue.filename || ""}`.replace(/^\//, "");
}

function embeddingHistoryRows(progress, currentFile) {
  const rows = Array.isArray(progress?.embedding_history)
    ? progress.embedding_history
    : [];
  const normalized = rows
    .map((row) => ({
      path: row.path || `${row.source_id || ""}/${row.filename || ""}`.replace(/^\//, ""),
      chars: Number(row.chars || row.prepared_chars || 0),
      chunks: Number(row.chunks || row.chunk_count || 0),
      chunkMs: Number(row.chunk_ms || row.chunking_ms || 0),
      status: row.status || "embedding",
      reason: row.reason || "",
      detail: row.detail || "",
    }))
    .filter((row) => row.path);
  if (normalized.length > 0) return normalized.slice(0, 8);
  if (!currentFile) return [];
  return [
    {
      path: currentFile,
      chars: Number(progress?.current_embedding_chars || 0),
      chunks: Number(progress?.current_embedding_chunks || 0),
      chunkMs: Number(progress?.current_embedding_chunk_ms || 0),
      status: "embedding",
      reason: "",
      detail: "",
    },
  ];
}

function activityStatusLabel(row) {
  if (row.status === "error") return t("crawler.index_progress.status.error");
  if (row.status === "skipped") return t("crawler.index_progress.status.skipped");
  return t("crawler.index_progress.status.embedding");
}

function activityMetrics(row) {
  if (row.status === "skipped" || row.status === "error") {
    const reason = getSkipReasonLabel(row.reason) || activityStatusLabel(row);
    const chars =
      row.chars > 0
        ? t("crawler.index_progress.metrics.chars_suffix", {
            chars: formatIndexNumber(row.chars),
          })
        : "";
    return `${reason}${chars}`;
  }
  const cut =
    row.chunkMs > 0
      ? t("crawler.index_progress.metrics.cut_suffix", {
          duration: formatDurationMs(row.chunkMs),
        })
      : "";
  return t("crawler.index_progress.metrics.active", {
    chars: formatIndexNumber(row.chars),
    chunks: formatIndexNumber(row.chunks),
    cut,
  });
}

export function createCollectionFinalLogMetadata(progress, jobId, collectionName) {
  const stats =
    progress?.statistics && typeof progress.statistics === "object"
      ? progress.statistics
      : {};
  const skipLog = Array.isArray(stats.skip_log)
    ? stats.skip_log
    : Array.isArray(progress?.skip_log)
      ? progress.skip_log
      : Array.isArray(progress?.recent_skips)
        ? progress.recent_skips
        : [];
  return {
    job_id: jobId || "",
    collection_name:
      collectionName || progress?.collection_name || t("crawler.modal.collection_default_name"),
    status: progress?.status || "unknown",
    source_ids: progress?.source_ids || stats.source_ids || [],
    processed_pages: progress?.processed_pages ?? stats.processed_pages ?? 0,
    total_pages: progress?.total_pages ?? stats.total_pages ?? 0,
    indexed_pages: progress?.indexed_pages ?? stats.indexed_pages ?? 0,
    prepared_pages: progress?.prepared_pages ?? stats.prepared_pages ?? 0,
    skipped_pages: progress?.skipped_pages ?? stats.skipped_pages ?? 0,
    total_chunks: progress?.total_chunks ?? stats.total_chunks ?? 0,
    prepared_chunks: progress?.prepared_chunks ?? stats.prepared_chunks ?? 0,
    deduped_chunks: progress?.deduped_chunks ?? stats.deduped_chunks ?? 0,
    skip_reasons: progress?.skip_reasons || stats.skip_reasons || {},
    prepare_original_chars:
      progress?.prepare_original_chars ?? stats.prepare_original_chars ?? 0,
    prepare_output_chars:
      progress?.prepare_output_chars ?? stats.prepare_output_chars ?? 0,
    prepare_removed_chars:
      progress?.prepare_removed_chars ?? stats.prepare_removed_chars ?? 0,
    empty_after_prepare_removed_chars:
      progress?.empty_after_prepare_removed_chars
      ?? stats.empty_after_prepare_removed_chars
      ?? 0,
    elapsed_ms: progress?.elapsed_ms ?? stats.elapsed_ms ?? 0,
    current_phase_elapsed_ms:
      progress?.current_phase_elapsed_ms ?? stats.current_phase_elapsed_ms ?? 0,
    phase_durations_ms:
      progress?.phase_durations_ms || stats.phase_durations_ms || {},
    parallel_embed_workers:
      progress?.parallel_embed_workers ?? stats.parallel_embed_workers ?? 0,
    embedding_history: progress?.embedding_history || stats.embedding_history || [],
    recent_skips: progress?.recent_skips || stats.recent_skips || [],
    skip_log: skipLog,
    skip_log_count:
      progress?.skip_log_count ?? stats.skip_log_count ?? skipLog.length,
    largest_prepare_removals:
      progress?.largest_prepare_removals || stats.largest_prepare_removals || [],
    errors: progress?.errors || stats.errors || [],
    error: progress?.error || stats.error || "",
  };
}

export default function CreateCollectionIndexProgress({
  progress,
  collectionName,
  variant,
  onOpenDetails = null,
}) {
  if (!progress) return null;
  const isRunning = progress.status === "running";
  const isSuccess = progress.status === "success";
  const isCancelled = progress.status === "cancelled";
  const sr = progress.skip_reasons || {};
  const skipEntries = Object.entries(sr).filter(([, n]) => n > 0);
  const phaseKey = progress.current_phase || "";
  const phaseLabel = getPhaseLabel(phaseKey);
  const phaseElapsedMs = Number(progress.current_phase_elapsed_ms || 0);
  const total = progress.total_pages || 0;
  const processed = progress.processed_pages ?? 0;
  const livePages = isRunning
    ? Math.max(
        Number(progress.indexed_pages || 0),
        Number(progress.prepared_pages || 0),
        Number(processed || 0),
      )
    : Number(progress.indexed_pages || 0);
  const liveChunks = isRunning
    ? Math.max(Number(progress.total_chunks || 0), Number(progress.prepared_chunks || 0))
    : Number(progress.total_chunks || 0);
  const pct =
    total > 0 ? Math.min(100, Math.round((100 * processed) / total)) : 0;
  const sourcesLabel = (progress.source_ids || []).join(", ") || "—";
  const currentFile =
    progress.current_filename &&
    `${progress.current_source_id || ""}/${progress.current_filename}`.replace(
      /^\//,
      "",
    );
  const embeddingRows = embeddingHistoryRows(progress, currentFile);
  const showEmbeddingHistory = isRunning && embeddingRows.length > 0;
  const phaseDurations = progress.phase_durations_ms || {};
  const elapsedMs = Number(progress.elapsed_ms || 0);
  const extraStats = [
    ["crawler.index_progress.extra.removed_chars", progress.prepare_removed_chars],
    ["crawler.index_progress.extra.prepared_chars", progress.prepare_output_chars],
    [
      "crawler.index_progress.extra.empty_page_removed",
      progress.empty_after_prepare_removed_chars,
    ],
    ["crawler.index_progress.extra.deduped_chunks", progress.deduped_chunks],
  ].filter(([, value]) => Number(value || 0) > 0);
  const timeStats = [
    ["crawler.index_progress.time.elapsed", elapsedMs],
    ["crawler.index_progress.time.embedding", phaseDurations.embedding],
    ["crawler.index_progress.time.chunking", phaseDurations.chunking],
    ["crawler.index_progress.time.prepare", phaseDurations.prepare],
    ["crawler.index_progress.time.saving", phaseDurations.saving],
  ].filter(([, value]) => Number(value || 0) > 0);
  const recentIssues =
    Array.isArray(progress.recent_skips) && progress.recent_skips.length > 0
      ? progress.recent_skips
      : (progress.errors || []).map((err) => ({ detail: String(err) }));
  const defaultCollectionName = t("crawler.modal.collection_default_name");
  const doneDuration =
    elapsedMs > 0
      ? t("crawler.index_progress.done_duration", {
          duration: formatDurationMs(elapsedMs),
        })
      : "";

  if (variant === "toast") {
    const sourceCount = (progress.source_ids || []).length;
    const topSkip = [...skipEntries].sort((a, b) => b[1] - a[1])[0];
    const errorsCount = progress.errors?.length || 0;

    return (
      <div className="create-collection-index-progress create-collection-index-progress--toast">
        {isRunning && (
          <div className="create-collection-toast-compact-status">
            <div
              className="create-collection-toast-spinner"
              aria-hidden="true"
              title={t("crawler.index_progress.indexing_in_progress")}
            />
            <div className="create-collection-toast-compact-status-text">
              <span>
                {phaseLabel || t("crawler.index_progress.indexing")}
                {phaseElapsedMs > 0 ? ` / ${formatDurationMs(phaseElapsedMs)}` : ""}
              </span>
              {sourceCount > 0 && (
                <span className="create-collection-toast-compact-muted">
                  {t("crawler.index_progress.source_count", { count: sourceCount })}
                </span>
              )}
            </div>
          </div>
        )}

        <div
          className="create-collection-toast-metrics"
          aria-label={t("crawler.index_progress.aria.progress")}
        >
          <span>
            <strong>{livePages}</strong>/{total || "..."}{" "}
            {t("crawler.index_progress.toast.processed")}
          </span>
          <span>
            <strong>{progress.skipped_pages ?? 0}</strong>{" "}
            {t("crawler.index_progress.stat.skipped")}
          </span>
          <span>
            <strong>{liveChunks}</strong> {t("crawler.index_progress.stat.chunks")}
          </span>
          {elapsedMs > 0 && (
            <span>
              <strong>{formatDurationMs(elapsedMs)}</strong>{" "}
              {t("crawler.index_progress.time.elapsed")}
            </span>
          )}
        </div>

        {isRunning && currentFile && (
          <div className="create-collection-toast-current" title={currentFile}>
            {currentFile}
          </div>
        )}

        {topSkip && (
          <div className="create-collection-toast-skip">
            {getSkipReasonLabel(topSkip[0]) || topSkip[0]}:{" "}
            <strong>{topSkip[1]}</strong>
          </div>
        )}

        {total > 0 && isRunning && (
          <div className="create-collection-toast-progress-bar-wrap create-collection-index-progress__bar">
            <div
              className="create-collection-toast-progress-bar-fill"
              style={{ width: `${pct}%` }}
            />
          </div>
        )}

        {isSuccess && (
          <div className="create-collection-toast-text">
            {t("crawler.index_progress.toast.success", {
              pages: progress.indexed_pages ?? 0,
              chunks: progress.total_chunks ?? 0,
              duration: doneDuration,
            })}
          </div>
        )}

        {isCancelled && (
          <div className="create-collection-toast-text">
            {t("crawler.index_progress.toast.cancelled", {
              processed,
              total: total || "...",
            })}
          </div>
        )}

        {errorsCount > 0 && (
          <div className="create-collection-toast-errors">
            {t("crawler.index_progress.toast.recent_errors", { count: errorsCount })}
          </div>
        )}

        {onOpenDetails && (
          <div className="create-collection-toast-actions">
            <button
              type="button"
              className="notification-center-card-action-btn create-collection-toast-action"
              onClick={onOpenDetails}
            >
              {t("crawler.index_progress.open_details")}
            </button>
          </div>
        )}
      </div>
    );
  }

  return (
    <div
      className={`create-collection-index-progress create-collection-index-progress--${variant}`}
    >
      {isRunning && (
        <div className="create-collection-index-progress__hero">
          <span
            className="create-collection-activity-ring"
            aria-hidden="true"
            title={t("crawler.index_progress.indexing_in_progress")}
          >
            <svg
              className="create-collection-activity-ring__svg"
              viewBox="0 0 48 48"
            >
              <circle
                className="create-collection-activity-ring__circle"
                cx="24"
                cy="24"
                r="18"
              />
            </svg>
          </span>
          <div className="create-collection-index-progress__hero-text">
            {variant === "modal" && (
              <div className="create-collection-index-progress__collection">
                {collectionName || defaultCollectionName}
              </div>
            )}
            <div className="create-collection-index-progress__sources">
              {t("crawler.index_progress.sources", { sources: sourcesLabel })}
            </div>
          </div>
        </div>
      )}

      <div className="create-collection-index-stats">
        <div className="create-collection-index-stat">
          <span className="create-collection-index-stat__value create-collection-index-stat__value--ok">
            {livePages} / {total || "…"}
          </span>
          <span className="create-collection-index-stat__label">
            {isRunning
              ? t("crawler.index_progress.stat.processed_total")
              : t("crawler.index_progress.stat.indexed_total")}
          </span>
        </div>
        <div className="create-collection-index-stat">
          <span className="create-collection-index-stat__value create-collection-index-stat__value--skip">
            {progress.skipped_pages ?? 0}
          </span>
          <span className="create-collection-index-stat__label">
            {t("crawler.index_progress.stat.skipped")}
          </span>
        </div>
        <div className="create-collection-index-stat">
          <span className="create-collection-index-stat__value">
            {liveChunks}
          </span>
          <span className="create-collection-index-stat__label">
            {t("crawler.index_progress.stat.chunks")}
          </span>
        </div>
      </div>

      {extraStats.length > 0 && (
        <div className="create-collection-index-extra-stats">
          {extraStats.map(([labelKey, value]) => (
            <span key={labelKey}>
              <strong>{formatIndexNumber(value)}</strong> {t(labelKey)}
            </span>
          ))}
        </div>
      )}

      {timeStats.length > 0 && (
        <div className="create-collection-index-extra-stats create-collection-index-extra-stats--timing">
          {timeStats.map(([labelKey, value]) => (
            <span key={labelKey}>
              <strong>{formatDurationMs(value)}</strong> {t(labelKey)}
            </span>
          ))}
        </div>
      )}

      {showEmbeddingHistory ? (
        <div className="create-collection-index-current create-collection-index-current--embedding-history">
          <div className="create-collection-index-current__phase">
            <span className="create-collection-index-current__phase-dot" />
            {phaseLabel}
            {phaseElapsedMs > 0 ? ` / ${formatDurationMs(phaseElapsedMs)}` : ""}
          </div>
          <div
            className="create-collection-embedding-history"
            aria-label={t("crawler.index_progress.embedding_history_aria")}
          >
            {embeddingRows.map((row, index) => (
              <div
                key={`${row.path}:${row.status}:${row.reason}:${row.chars}:${row.chunks}:${row.chunkMs}`}
                className={`create-collection-embedding-history__row create-collection-embedding-history__row--${row.status}`}
                style={{
                  "--embedding-history-opacity": Math.max(0.4, 1 - index * 0.15),
                  "--embedding-history-font-size": `${13 - index * 0.5}px`,
                  "--embedding-history-delay": `${index * 28}ms`,
                }}
                title={row.detail ? `${row.path}: ${row.detail}` : row.path}
              >
                <span className="create-collection-embedding-history__file-wrap">
                  <span className={`create-collection-embedding-history__status create-collection-embedding-history__status--${row.status}`}>
                    {activityStatusLabel(row)}
                  </span>
                  <span className="create-collection-embedding-history__file">
                    {row.path}
                  </span>
                </span>
                <span className="create-collection-embedding-history__metrics">
                  {activityMetrics(row)}
                </span>
              </div>
            ))}
          </div>
        </div>
      ) : isRunning && (currentFile || phaseLabel) && (
        <div className="create-collection-index-current">
          {phaseLabel && phaseKey && (
            <div className="create-collection-index-current__phase">
              <span className="create-collection-index-current__phase-dot" />
              {phaseLabel}
              {phaseElapsedMs > 0 ? ` / ${formatDurationMs(phaseElapsedMs)}` : ""}
            </div>
          )}
          {currentFile && (
            <div
              className="create-collection-index-current__file"
              title={currentFile}
            >
              {currentFile}
            </div>
          )}
        </div>
      )}

      {skipEntries.length > 0 && (
        <div className="create-collection-index-skips">
          <div className="create-collection-index-skips__title">
            {t("crawler.index_progress.skip_reasons_title")}
          </div>
          <div className="create-collection-index-skips__pills">
            {skipEntries.map(([key, n]) => (
              <span key={key} className="create-collection-index-skip-pill">
                {getSkipReasonLabel(key) || key}: <strong>{n}</strong>
              </span>
            ))}
          </div>
        </div>
      )}

      {total > 0 && isRunning && (
        <div className="create-collection-toast-progress-bar-wrap create-collection-index-progress__bar">
          <div
            className="create-collection-toast-progress-bar-fill"
            style={{ width: `${pct}%` }}
          />
        </div>
      )}

      {isSuccess && (
        <div className="create-collection-index-done">
          {t("crawler.index_progress.done_success", {
            indexed: progress.indexed_pages ?? 0,
            skipped: progress.skipped_pages ?? 0,
            chunks: progress.total_chunks ?? 0,
            duration: doneDuration,
          })}
        </div>
      )}

      {isCancelled && (
        <div className="create-collection-index-done">
          {t("crawler.index_progress.done_cancelled", {
            processed,
            total: total || "...",
          })}
        </div>
      )}

      {recentIssues.length > 0 && (
        <details className="create-collection-index-errors">
          <summary>
            {t("crawler.index_progress.recent_issues", {
              count: recentIssues.length,
            })}
          </summary>
          <div className="create-collection-index-errors__list">
            {recentIssues.map((issue, i) => (
              <div key={i} className="create-collection-index-error-item">
                {issuePath(issue) && (
                  <span className="create-collection-index-error-file">
                    {issuePath(issue)}
                  </span>
                )}
                {issue.reason && (
                  <span className="create-collection-index-error-reason">
                    {getSkipReasonLabel(issue.reason) || issue.reason}
                  </span>
                )}
                {issue.detail && (
                  <span className="create-collection-index-error-detail">
                    {issue.detail}
                  </span>
                )}
                {Number(issue.removed_chars || 0) > 0 && (
                  <span className="create-collection-index-error-meta">
                    {t("crawler.index_progress.removed_chars", {
                      count: formatIndexNumber(issue.removed_chars),
                    })}
                  </span>
                )}
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
