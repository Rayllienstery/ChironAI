import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import CoreUIBadge from "./CoreUIBadge";
import CoreUIButton from "./CoreUIButton";
import CoreUIPillTabs from "./CoreUIPillTabs";
import { useOptionalNotificationCenter } from "./NotificationCenterContext";
import {
  checkDockerImageUpdate,
  disableExtension,
  enableExtension,
  getExtensionInstalled,
  getExtensionDetails,
  getExtensionProviders,
  getExtensionRegistry,
  getExtensionUiPayload,
  installExtension,
  installExtensionTarget,
  killExtensionSandbox,
  removeExtension,
  restartExtensionSandbox,
  updateDockerImage,
  updateExtensionDocker,
} from "../services/api";
import "../styles/components/ExtensionsTab.css";

const EXTENSION_VIEWS = [
  { id: "installed", label: "Installed" },
  { id: "providers", label: "Providers" },
  { id: "registry", label: "Registry" },
];

const DOCKER_UPDATE_STEPS = [
  { id: "check", label: "Check remote image digest" },
  { id: "pull", label: "Pull Docker image", hint: "Large images can take several minutes." },
  { id: "recreate", label: "Recreate container with preserved volumes" },
  { id: "health", label: "Wait for service health check" },
];

function formatElapsedSeconds(totalSeconds) {
  const seconds = Math.max(0, Number(totalSeconds) || 0);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  const remainder = seconds % 60;
  return `${minutes}m ${remainder}s`;
}

function dockerUpdateStepIndex(stepId) {
  return DOCKER_UPDATE_STEPS.findIndex((step) => step.id === stepId);
}

function ExtensionDockerUpdatePanel({ progress, compact = false }) {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    if (!progress) return undefined;
    const timer = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [progress]);

  if (!progress) return null;

  const activeIndex = dockerUpdateStepIndex(progress.step);
  const elapsed = formatElapsedSeconds(Math.floor((nowMs - progress.startedAt) / 1000));
  const bulkLabel =
    progress.totalCount > 1
      ? `Extension ${progress.currentIndex + 1} of ${progress.totalCount}`
      : null;

  return (
    <section
      className={`extensions-docker-update-panel${compact ? " extensions-docker-update-panel--compact" : ""}`}
      aria-live="polite"
      aria-busy="true"
    >
      {compact ? (
        <div className="extensions-docker-update-panel__meta">
          <span className="extensions-docker-update-panel__meta-image">{progress.image}</span>
          {bulkLabel ? <CoreUIBadge tone="neutral">{bulkLabel}</CoreUIBadge> : null}
          <CoreUIBadge tone="info">{elapsed}</CoreUIBadge>
        </div>
      ) : (
        <div className="extensions-docker-update-panel__header">
          <span className="extensions-docker-update-panel__spinner" aria-hidden="true" />
          <div>
            <strong>{progress.title}</strong>
            <p>
              {bulkLabel ? `${bulkLabel} · ` : ""}
              {progress.image}
            </p>
          </div>
          <CoreUIBadge tone="info">{elapsed}</CoreUIBadge>
        </div>
      )}

      {progress.step === "pull" ? (
        <div className="extensions-docker-update-panel__progress" aria-hidden="true">
          <div className="extensions-docker-update-panel__progress-bar" />
        </div>
      ) : null}

      <ol className="extensions-docker-update-steps">
        {DOCKER_UPDATE_STEPS.map((step, index) => {
          const done = activeIndex > index || progress.step === "done";
          const active = progress.step === step.id;
          const tone = done ? "success" : active ? "info" : "neutral";
          return (
            <li
              key={step.id}
              className={`extensions-docker-update-step${active ? " extensions-docker-update-step--active" : ""}${done ? " extensions-docker-update-step--done" : ""}`}
            >
              <span className="extensions-docker-update-step__icon material-symbols-outlined" aria-hidden="true">
                {done ? "check_circle" : active ? "progress_activity" : "radio_button_unchecked"}
              </span>
              <div className="extensions-docker-update-step__copy">
                <span>{step.label}</span>
                {active && step.hint ? <small>{step.hint}</small> : null}
                {active && progress.detail ? <small>{progress.detail}</small> : null}
              </div>
              {active ? <CoreUIBadge tone={tone}>Running</CoreUIBadge> : null}
              {done ? <CoreUIBadge tone={tone}>Done</CoreUIBadge> : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function ExtensionIcon({ icon, iconUrl }) {
  const url = String(iconUrl || "").trim();
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [url]);

  if (url && !imageFailed) {
    const isSvg = url.toLowerCase().endsWith(".svg") || url.toLowerCase().includes(".svg?");
    const isRemote = /^https?:\/\//i.test(url);
    if (isSvg && !isRemote) {
      return (
        <span
          className="extensions-card__icon extensions-card__icon--masked"
          style={{
            maskImage: `url(${url})`,
            WebkitMaskImage: `url(${url})`,
          }}
          aria-hidden="true"
        />
      );
    }
    return (
      <img
        className="extensions-card__icon extensions-card__icon--image"
        src={url}
        alt=""
        aria-hidden="true"
        loading="lazy"
        onError={() => setImageFailed(true)}
      />
    );
  }

  const iconText = String(icon || "").trim();
  if (iconText && !iconText.includes("/") && !iconText.includes("\\") && !/\.(svg|png|jpg|jpeg|webp|gif)$/i.test(iconText)) {
    return (
      <span className="material-symbols-outlined extensions-card__icon" aria-hidden="true">
        {iconText}
      </span>
    );
  }

  return (
    <span className="material-symbols-outlined extensions-card__icon" aria-hidden="true">
      extension
    </span>
  );
}

function hasDockerContainer(item) {
  return Boolean(item?.docker?.container_name || item?.docker?.image);
}

function dockerUpdateAvailable(item) {
  return Boolean(item?.docker?.update_available);
}

function formatDockerVersionLabel(docker) {
  if (!docker) return "";
  const current = String(docker.current_version || "").trim();
  const update = String(docker.update_version || "").trim();
  const image = String(docker.image || "").trim();
  if (docker.update_available && current && update && current !== update) {
    return `${current} → ${update}`;
  }
  if (docker.update_available && update) {
    return update === current ? `${current || image} (update available)` : `${current || image} → ${update}`;
  }
  if (docker.update_status === "up_to_date" && current) {
    return `${current} (up to date)`;
  }
  if (current) return current;
  return image;
}

function HealthPill({ health }) {
  const status = String(health?.status || "unknown");
  const tone =
    status === "ok" || status === "loaded" || status === "installed"
      ? "success"
      : status === "unreachable" || status === "failed" || status === "error"
        ? "error"
        : "neutral";
  return <CoreUIBadge tone={tone}>{status}</CoreUIBadge>;
}

function ExtensionCardCopy({ title, description, fallbackDescription = "No description." }) {
  return (
    <div className="extensions-card__copy">
      <h4>{title}</h4>
      <p>{description || fallbackDescription}</p>
    </div>
  );
}

function SecurityFindings({ findings }) {
  const rows = Array.isArray(findings) ? findings : [];
  if (!rows.length) return null;
  return (
    <div className="extensions-card__details extensions-security-findings">
      <div className="extensions-schema-label">Security findings</div>
      <ul>
        {rows.slice(0, 5).map((finding, index) => (
          <li key={`${finding.code || 'finding'}:${finding.file || ''}:${finding.line || index}`}>
            <strong>{finding.severity || 'finding'}</strong>
            {finding.code ? ` ${finding.code}` : ''}: {finding.message || 'Security audit finding'}
            {finding.file ? ` (${finding.file}${finding.line ? `:${finding.line}` : ''})` : ''}
          </li>
        ))}
      </ul>
    </div>
  );
}

function CapabilityList({ capabilities }) {
  const rows = Array.isArray(capabilities) ? capabilities : [];
  if (!rows.length) return null;
  return (
    <div className="extensions-capabilities">
      {rows.slice(0, 8).map((capability) => (
        <CoreUIBadge
          key={capability.id || capability.label}
          tone={capability.risk === "high" || capability.risk === "critical" ? "warning" : "neutral"}
        >
          {capability.label || capability.id}
        </CoreUIBadge>
      ))}
    </div>
  );
}

function ExtensionDetailsModal({
  details,
  selectedRef,
  setSelectedRef,
  manualRef,
  setManualRef,
  busy,
  onInstall,
  onClose,
}) {
  if (!details) return null;
  const entry = details.entry || {};
  const versions = Array.isArray(details.versions) ? details.versions : [];
  const selectedVersion = versions.find((version) => (version.ref || version.version) === selectedRef) || details.latest || {};
  const readme = details.readme || {};
  const publisher = details.publisher || entry.publisher || {};
  const effectiveRef = manualRef.trim() || selectedRef || selectedVersion.ref || selectedVersion.version || "";
  const provenance = manualRef.trim() ? "branch_or_commit_archive" : selectedVersion.provenance_level || "unknown";
  const weakProvenance = ["github_tag_archive", "branch_or_commit_archive", "unknown"].includes(provenance);

  return (
    <div className="extensions-modal-backdrop" role="presentation" onMouseDown={onClose}>
      <div className="extensions-modal" role="dialog" aria-modal="true" aria-labelledby="extension-details-title" onMouseDown={(event) => event.stopPropagation()}>
        <div className="extensions-modal__header">
          <div className="extensions-card__title-row">
            <ExtensionIcon icon={entry.icon} iconUrl={entry.icon_url} />
            <div>
              <h3 id="extension-details-title">{entry.title || entry.id}</h3>
              <p>{entry.description || ""}</p>
            </div>
          </div>
          <CoreUIBadge tone="info">Not installed</CoreUIBadge>
          <CoreUIButton variant="ghost" onClick={onClose}>
            Close
          </CoreUIButton>
        </div>

        <div className="extensions-modal__toolbar">
          <label className="extensions-modal__field">
            <span>Version</span>
            <select value={selectedRef} onChange={(event) => setSelectedRef(event.target.value)}>
              {!versions.length ? <option value="">unavailable</option> : null}
              {versions.map((version) => {
                const ref = version.ref || version.version;
                return (
                  <option key={ref} value={ref}>
                    {version.is_latest ? `${ref} latest` : ref}
                  </option>
                );
              })}
            </select>
          </label>
          <label className="extensions-modal__field">
            <span>Ref</span>
            <input value={manualRef} onChange={(event) => setManualRef(event.target.value)} placeholder="branch, tag, or commit" />
          </label>
          <CoreUIButton
            variant="primary"
            disabled={busy || !effectiveRef}
            onClick={() =>
              onInstall({
                version: effectiveRef,
                ref: effectiveRef,
                target_kind: manualRef.trim() ? "branch" : selectedVersion.target_kind || "release",
                archive_url: manualRef.trim() ? "" : selectedVersion.archive_url || "",
              })
            }
          >
            Install
          </CoreUIButton>
        </div>

        <div className="extensions-modal__meta">
          <span>Publisher: {publisher.name || "unknown"}</span>
          <span>Trust: {publisher.trust_state || entry.visibility || "unknown"}</span>
          <span>Repository: {entry.repository_id || entry.repository || "unknown"}</span>
          <span>Provenance: {provenance}</span>
          {selectedVersion.digest ? <span>Digest: sha256:{selectedVersion.digest}</span> : null}
        </div>
        <CapabilityList capabilities={entry.capabilities} />
        {weakProvenance ? (
          <div className="coreui-panel-note coreui-panel-note--warning">
            Weak provenance: {provenance}
          </div>
        ) : null}
        {Array.isArray(details.warnings) && details.warnings.length ? (
          <div className="coreui-panel-note coreui-panel-note--warning">{details.warnings.join(" | ")}</div>
        ) : null}
        <pre className="extensions-readme">{readme.markdown || readme.error || "README unavailable."}</pre>
      </div>
    </div>
  );
}

function SandboxDiagnostics({ item, busyId, runAction }) {
  if (!item?.sandboxed) return null;
  const status = item.sandbox_status || "ready";
  const lastError = item.sandbox_last_error || item.sandbox_error || "";
  const canRestart = item.sandbox_can_restart !== false || ["manual_stop", "blocked", "crashed", "timeout", "protocol_error"].includes(status);
  return (
    <div className="extensions-card__details extensions-sandbox-diagnostics">
      <div className="extensions-sandbox-diagnostics__grid">
        <div>
          <span className="extensions-schema-label">Worker PID</span>
          <strong>{item.sandbox_pid || "not running"}</strong>
        </div>
        <div>
          <span className="extensions-schema-label">Sandbox status</span>
          <strong>{status}</strong>
        </div>
        <div>
          <span className="extensions-schema-label">Restart count</span>
          <strong>{Number(item.sandbox_restart_count || 0)}</strong>
        </div>
        <div>
          <span className="extensions-schema-label">Restart policy</span>
          <strong>{item.sandbox_blocked ? "manual restart required" : "auto retry 2x"}</strong>
        </div>
      </div>
      {lastError ? <pre className="extensions-card__error">{lastError}</pre> : null}
      <div className="extensions-sandbox-diagnostics__actions">
        <CoreUIButton
          variant="primary"
          disabled={busyId === item.id || !canRestart}
          onClick={() => runAction(item.id, (id) => restartExtensionSandbox(id), "restart")}
        >
          Restart worker
        </CoreUIButton>
        <CoreUIButton
          variant="danger"
          disabled={busyId === item.id || !item.sandbox_can_kill}
          onClick={() => runAction(item.id, (id) => killExtensionSandbox(id), "kill")}
        >
          Kill worker
        </CoreUIButton>
      </div>
    </div>
  );
}

function SchemaRenderer({ schema, providerByExtensionId }) {
  const pages = Array.isArray(schema?.pages) ? schema.pages : [];
  if (!pages.length) return null;

  const renderComponent = (component, extensionId) => {
    const type = String(component?.type || "").toLowerCase();
    const key = String(component?.key || component?.label || type);
    const provider = providerByExtensionId.get(extensionId);
    if (type === "status") {
      return (
        <div key={key} className="extensions-schema-row">
          <span className="extensions-schema-label">{component.label || "Status"}</span>
          <HealthPill health={provider?.health} />
        </div>
      );
    }
    if (type === "text") {
      return (
        <div key={key} className="extensions-schema-text">
          <div className="extensions-schema-label">{component.label || "Info"}</div>
          <p>
            {key === "provider_summary"
              ? provider
                ? `${provider.title} via ${provider.provider_id}`
                : "Provider not loaded in this process."
              : String(component.text || component.value || "")}
          </p>
        </div>
      );
    }
    if (type === "table") {
      const rows = key === "provider_models" ? provider?.models || [] : [];
      const columns = Array.isArray(component.columns) ? component.columns : [];
      return (
        <div key={key} className="extensions-schema-table-wrap">
          <div className="extensions-schema-label">{component.label || "Table"}</div>
          <table className="extensions-schema-table">
            <thead>
              <tr>
                {columns.map((column) => (
                  <th key={column.key}>{column.label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.length ? (
                rows.map((row) => (
                  <tr key={row.id}>
                    {columns.map((column) => (
                      <td key={`${row.id}:${column.key}`}>{row[column.key] ?? ""}</td>
                    ))}
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={Math.max(1, columns.length)}>No rows available.</td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      );
    }
    if (type === "diagnostics") {
      return (
        <div key={key} className="extensions-schema-diagnostics">
          <div className="extensions-schema-label">{component.label || "Diagnostics"}</div>
          <pre>{JSON.stringify(provider?.health?.details || {}, null, 2)}</pre>
        </div>
      );
    }
    return (
      <div key={key} className="extensions-schema-unsupported">
        Unsupported schema component: {type}
      </div>
    );
  };

  return (
    <div className="extensions-schema">
      {pages.map((page) => (
        <div key={page.id || page.title} className="extensions-schema-page">
          <h3>{page.title || "Page"}</h3>
          {Array.isArray(page.sections)
            ? page.sections.map((section) => (
                <section key={section.id || section.title} className="coreui-card-shell coreui-p-md extensions-schema-section">
                  <div className="extensions-schema-section-header">
                    <h4>{section.title || "Section"}</h4>
                  </div>
                  <div className="extensions-schema-section-body">
                    {(Array.isArray(section.components) ? section.components : []).map((component) =>
                      renderComponent(component, page.extensionId)
                    )}
                  </div>
                </section>
              ))
            : null}
        </div>
      ))}
    </div>
  );
}

/**
 * Extensions management tab. Surfaces installed extensions, the GitHub
 * registry, providers, and per-extension tab UI payloads. Calls into the
 * extensions_backend service for install/update/remove.
 *
 * @param {{ onErrorStateChange?: (hasError: boolean) => void, onExtensionSurfaceChange?: () => void | Promise<void> }} [props] -
 *   Notified when this tab transitions into/out of an error state and when
 *   extension navigation/service surface should be refreshed.
 */
export default function ExtensionsTab({ onErrorStateChange, onExtensionSurfaceChange }) {
  const notificationCenter = useOptionalNotificationCenter();
  const [activeView, setActiveView] = useState("installed");
  const [registry, setRegistry] = useState([]);
  const [registryDiagnostics, setRegistryDiagnostics] = useState([]);
  const [installed, setInstalled] = useState([]);
  const [providers, setProviders] = useState([]);
  const [uiPayload, setUiPayload] = useState({ extensions: [], failed: [] });
  const [busyId, setBusyId] = useState("");
  const [dockerUpdateBusy, setDockerUpdateBusy] = useState("");
  const [dockerUpdateProgress, setDockerUpdateProgress] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [registryLoading, setRegistryLoading] = useState(false);
  const [details, setDetails] = useState(null);
  const [detailsLoading, setDetailsLoading] = useState(false);
  const [selectedRef, setSelectedRef] = useState("");
  const [manualRef, setManualRef] = useState("");
  const persistExtensionNotification = notificationCenter?.persistNotification;

  const loadRegistry = useCallback(async ({ forceRefresh = false, notifyOnError = false } = {}) => {
    setRegistryLoading(true);
    try {
      const data = await getExtensionRegistry({ forceRefresh });
      setRegistry(data.registry || []);
      setRegistryDiagnostics(data.diagnostics || []);
    } catch (e) {
      const msg = String(e?.message || e || "Failed to load extension registry");
      setRegistryDiagnostics([{ severity: "error", code: "registry_load_failed", message: msg }]);
      if (notifyOnError && persistExtensionNotification) {
        void persistExtensionNotification({
          kind: "error",
          source: "extensions",
          title: "Extensions registry",
          message: msg,
          metadata: { operation: "registry_load" },
          aggregation_key: "extensions-registry:load:error",
        });
      }
    } finally {
      setRegistryLoading(false);
    }
  }, [persistExtensionNotification]);

  const loadAll = useCallback(async (forceRefresh = false) => {
    setLoading(true);
    setError("");
    void loadRegistry({ forceRefresh, notifyOnError: forceRefresh });
    const results = await Promise.allSettled([
        getExtensionInstalled(),
        getExtensionProviders(),
        getExtensionUiPayload(),
    ]);
    const [installedResult, providersResult, uiResult] = results;
    const failures = [];

    if (installedResult.status === "fulfilled") {
      setInstalled(installedResult.value.extensions || []);
    } else {
      failures.push(installedResult.reason);
    }
    if (providersResult.status === "fulfilled") {
      setProviders(providersResult.value.providers || []);
    } else {
      failures.push(providersResult.reason);
    }
    if (uiResult.status === "fulfilled") {
      const uiData = uiResult.value;
      setUiPayload({ extensions: uiData.extensions || [], failed: uiData.failed || [] });
    } else {
      failures.push(uiResult.reason);
    }

    if (failures.length) {
      const msg = failures
        .map((item) => String(item?.message || item || "Failed to load extensions"))
        .join("; ");
      setError(msg);
      if (persistExtensionNotification) {
        void persistExtensionNotification({
          kind: "error",
          source: "extensions",
          title: "Extensions",
          message: msg,
          metadata: { operation: "extensions_load" },
          aggregation_key: "extensions:load:error",
        });
      }
      onErrorStateChange?.(true);
    } else {
      onErrorStateChange?.(false);
    }
    setLoading(false);
  }, [loadRegistry, onErrorStateChange, persistExtensionNotification]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  // Refresh registry (using server cache) when the user navigates to the
  // Registry sub-tab so the list is up-to-date without hammering GitHub.
  // Force-refresh is only triggered by the explicit Refresh button.
  const prevActiveViewRef = useRef(null);
  useEffect(() => {
    if (activeView === "registry" && prevActiveViewRef.current !== "registry") {
      void loadRegistry();
    }
    prevActiveViewRef.current = activeView;
  }, [activeView, loadRegistry]);

  const installedById = useMemo(
    () => new Map(installed.map((item) => [item.id, item])),
    [installed]
  );
  const dockerExtensions = useMemo(
    () => installed.filter((item) => hasDockerContainer(item)),
    [installed]
  );
  const dockerUpdatesAvailable = useMemo(
    () => dockerExtensions.filter((item) => dockerUpdateAvailable(item)),
    [dockerExtensions]
  );
  const providerByExtensionId = useMemo(
    () => new Map(providers.map((item) => [item.extension_id, item])),
    [providers]
  );
  const extensionTitle = useCallback(
    (extensionId) => {
      const installedItem = installedById.get(extensionId);
      if (installedItem?.title) return installedItem.title;
      const registryItem = registry.find((item) => item.id === extensionId);
      return registryItem?.title || extensionId;
    },
    [installedById, registry]
  );
  const notifyExtensionEvent = useCallback(
    (extensionId, operation, kind, message, metadata = {}) => {
      if (!persistExtensionNotification || !extensionId) return;
      const title = extensionTitle(extensionId);
      const persistedKind = kind === "error" ? "error" : "info";
      void persistExtensionNotification({
        kind: persistedKind,
        source: "extensions",
        title: `${title}: ${operation}`,
        message,
        metadata: {
          extension_id: extensionId,
          operation,
          outcome: kind,
          ...metadata,
        },
        aggregation_key: `extensions-lifecycle:${extensionId}:${operation}:${kind}`,
      });
    },
    [extensionTitle, persistExtensionNotification]
  );
  const viewTabs = useMemo(
    () =>
      EXTENSION_VIEWS.map((view) => ({
        ...view,
        count:
          view.id === "registry"
            ? registry.length
            : view.id === "installed"
              ? installed.length
              : view.id === "providers"
                ? providers.length
                : view.id === "ui"
                  ? (uiPayload.extensions || []).length
                  : 0,
      })),
    [installed.length, providers.length, registry.length, uiPayload.extensions]


  );

  const runAction = useCallback(
    async (extensionId, fn, operation = "action") => {
      setBusyId(extensionId);
      setError("");
      try {
        const result = await fn(extensionId);
        notifyExtensionEvent(extensionId, operation, "success", `${operation} completed.`, result || {});
        await loadAll();
        await onExtensionSurfaceChange?.();
        onErrorStateChange?.(false);
      } catch (e) {
        const msg = String(e?.message || e || "Action failed");
        setError(msg);
        notifyExtensionEvent(extensionId, operation, "error", msg);
        onErrorStateChange?.(true);
      } finally {
        setBusyId("");
      }
    },
    [loadAll, notifyExtensionEvent, onErrorStateChange, onExtensionSurfaceChange]
  );

  const openDetails = useCallback(
    async (item) => {
      if (!item?.id || installedById.has(item.id)) return;
      setDetailsLoading(true);
      setError("");
      try {
        const payload = await getExtensionDetails(item.id);
        const versions = Array.isArray(payload.versions) ? payload.versions : [];
        const latestRef = payload.latest?.ref || payload.latest?.version || versions[0]?.ref || versions[0]?.version || "";
        setDetails(payload);
        setSelectedRef(latestRef);
        setManualRef("");
      } catch (e) {
        const msg = String(e?.message || e || "Failed to load extension details");
        setError(msg);
        notifyExtensionEvent(item.id, "details", "error", msg);
        onErrorStateChange?.(true);
      } finally {
        setDetailsLoading(false);
      }
    },
    [installedById, notifyExtensionEvent, onErrorStateChange]
  );

  const installFromDetails = useCallback(
    async (target) => {
      const extId = details?.entry?.id;
      const extTitle = details?.entry?.title || extId;
      if (!extId) return;

      // Close modal immediately so the user isn't blocked waiting.
      setDetails(null);
      setBusyId(extId);
      setError("");

      // Show a progress notification right away.
      let loadingNotifId = null;
      if (persistExtensionNotification) {
        loadingNotifId = await persistExtensionNotification({
          kind: "loading",
          source: "extensions",
          title: `${extTitle}: installing`,
          message: `Downloading and installing from GitHub…`,
          metadata: { extension_id: extId, operation: "install" },
          aggregation_key: `extensions-lifecycle:${extId}:install:loading`,
        });
      }

      try {
        const result = await installExtensionTarget(extId, target);
        if (loadingNotifId != null) notificationCenter?.dismissPersisted?.(loadingNotifId);
        notifyExtensionEvent(
          extId,
          "install",
          "success",
          `Installed ${result?.selected_ref || result?.version || target?.ref || target?.version || "selected version"}.`,
          result || {}
        );
        await loadAll();
        await onExtensionSurfaceChange?.();
        onErrorStateChange?.(false);
      } catch (e) {
        if (loadingNotifId != null) notificationCenter?.dismissPersisted?.(loadingNotifId);
        const msg = String(e?.message || e || "Install failed");
        setError(msg);
        notifyExtensionEvent(extId, "install", "error", msg);
        onErrorStateChange?.(true);
      } finally {
        setBusyId("");
      }
    },
    [details, loadAll, notificationCenter, notifyExtensionEvent, onErrorStateChange, onExtensionSurfaceChange, persistExtensionNotification]
  );

  const runDockerUpdate = useCallback(
    async (extensionIds) => {
      const ids = (Array.isArray(extensionIds) ? extensionIds : [extensionIds]).filter(Boolean);
      if (!ids.length) return;

      const targets = ids
        .map((id) => {
          const item = installedById.get(id);
          const image = String(item?.docker?.image || "").trim();
          if (!image) return null;
          return { id, title: extensionTitle(id), image, item };
        })
        .filter(Boolean);
      if (!targets.length) {
        setError("No Docker image is configured for the selected extension(s).");
        return;
      }

      const busyKey = targets.length === 1 ? targets[0].id : "__bulk__";
      const liveActivityId = `extensions-docker:${busyKey}`;
      const startedAt = Date.now();
      setDockerUpdateBusy(busyKey);
      setError("");

      const pushProgress = (patch) => {
        setDockerUpdateProgress((prev) => {
          const base = prev || {
            busyKey,
            startedAt,
            totalCount: targets.length,
            currentIndex: 0,
            title: targets[0].title,
            image: targets[0].image,
            step: "check",
          };
          return { ...base, ...patch };
        });
      };

      pushProgress({
        busyKey,
        startedAt,
        totalCount: targets.length,
        currentIndex: 0,
        title: targets[0].title,
        image: targets[0].image,
        step: "check",
        detail: "",
      });

      try {
        const results = [];

        for (let index = 0; index < targets.length; index += 1) {
          const target = targets[index];
          pushProgress({
            currentIndex: index,
            title: target.title,
            image: target.image,
            step: "check",
            detail: "Comparing local and remote digests…",
          });

          const check = await checkDockerImageUpdate(target.image);
          if (!check?.ok && check?.error) {
            throw new Error(check.error || check.details || `Failed to check ${target.image}`);
          }

          pushProgress({
            step: "pull",
            detail: check?.status === "up_to_date"
              ? "Image is up to date; refreshing local layers anyway…"
              : "Downloading image layers from the registry…",
          });
          const pulled = await updateDockerImage(target.image);
          if (!pulled?.ok) {
            throw new Error(pulled?.error || pulled?.details || `Failed to pull ${target.image}`);
          }

          pushProgress({
            step: "recreate",
            detail: "Stopping the old container and starting a new one with the same volumes…",
          });
          const recreated = await updateExtensionDocker([target.id], { skipImagePull: true });
          if (!recreated?.ok) {
            throw new Error(recreated?.error || recreated?.message || `Failed to recreate ${target.title}`);
          }

          pushProgress({
            step: "health",
            detail: recreated?.message || "Verifying service health…",
          });
          results.push(recreated);
        }

        const successMsg =
          results.length === 1
            ? results[0]?.message || `Updated ${targets[0].title}.`
            : `Updated ${results.length} extension containers.`;

        pushProgress({ step: "done", detail: successMsg });
        notifyExtensionEvent(
          targets[0].id,
          "docker update",
          "success",
          successMsg,
          { extension_ids: ids, results }
        );
        await loadAll();
        await onExtensionSurfaceChange?.();
        onErrorStateChange?.(false);
      } catch (e) {
        const msg = String(e?.message || e || "Docker update failed");
        setError(msg);
        notifyExtensionEvent(targets[0].id, "docker update", "error", msg, { extension_ids: ids });
        onErrorStateChange?.(true);
      } finally {
        notificationCenter?.clearLiveActivity?.(liveActivityId);
        setDockerUpdateBusy("");
        setDockerUpdateProgress(null);
      }
    },
    [
      extensionTitle,
      installedById,
      loadAll,
      notificationCenter,
      notifyExtensionEvent,
      onErrorStateChange,
      onExtensionSurfaceChange,
      persistExtensionNotification,
    ]
  );

  useEffect(() => {
    if (!dockerUpdateProgress) return undefined;
    const liveActivityId = `extensions-docker:${dockerUpdateProgress.busyKey}`;
    notificationCenter?.setLiveActivity?.(
      liveActivityId,
      "extensions",
      <ExtensionDockerUpdatePanel progress={dockerUpdateProgress} compact />,
      {
        headerLeading: (
          <span className="extensions-docker-update-live-title">
            <span
              className="extensions-docker-update-panel__spinner extensions-docker-update-panel__spinner--inline"
              aria-hidden="true"
            />
            <span>{dockerUpdateProgress.title}</span>
          </span>
        ),
      }
    );
    return undefined;
  }, [dockerUpdateProgress, notificationCenter]);

  const renderDockerUpdateButton = (item, { stopPropagation = false } = {}) => {
    if (!hasDockerContainer(item)) return null;
    const isBusy = dockerUpdateBusy === item.id || dockerUpdateBusy === "__bulk__" || busyId === item.id;
    const handler = stopPropagation
      ? (event) => {
          event.stopPropagation();
          void runDockerUpdate(item.id);
        }
      : () => void runDockerUpdate(item.id);

    return (
      <CoreUIButton
        variant={dockerUpdateAvailable(item) ? "primary" : "default"}
        disabled={isBusy}
        onClick={handler}
        title={
          item.docker?.data_persisted
            ? `${item.docker?.update_message || "Pull the latest Docker image and restart the service."} Models and data stay on the mounted Docker volume(s).`
            : item.docker?.update_message || "Pull the latest container image and restart the service"
        }
      >
        {dockerUpdateBusy === item.id || (dockerUpdateBusy === "__bulk__" && dockerUpdateAvailable(item))
          ? "Updating…"
          : "Update"}
      </CoreUIButton>
    );
  };

  return (
    <div className="extensions-tab tab-view">
      <div className="extensions-tab__header">
        <div>
          <h2>Extensions</h2>
          <p>Trusted registry, installed providers, and declarative CoreUI schemas.</p>
        </div>
        <div className="extensions-tab__header-actions">
          {dockerUpdatesAvailable.length > 0 ? (
            <CoreUIButton
              variant="ghost"
              onClick={() => runDockerUpdate(dockerUpdatesAvailable.map((item) => item.id))}
              disabled={loading || Boolean(busyId) || Boolean(dockerUpdateBusy)}
            >
              Update containers ({dockerUpdatesAvailable.length})
            </CoreUIButton>
          ) : null}
          <CoreUIButton variant="primary" onClick={() => loadAll(true)} disabled={loading || registryLoading || Boolean(busyId) || Boolean(dockerUpdateBusy)}>
            Refresh
          </CoreUIButton>
        </div>
      </div>

      <CoreUIPillTabs
        tabs={viewTabs}
        value={activeView}
        onChange={setActiveView}
        ariaLabel="Extension views"
        getLabel={(tab) => (
          <span className="extensions-view-tab-label">
            <span>{tab.label}</span>
            <CoreUIBadge>{tab.count}</CoreUIBadge>
          </span>
        )}
      />

      {error ? <div className="coreui-panel-note coreui-panel-note--error">{error}</div> : null}
      {dockerUpdateProgress ? (
        <section className="app-default-card extensions-docker-update-shell" aria-label="Extension container update progress">
          <ExtensionDockerUpdatePanel progress={dockerUpdateProgress} />
        </section>
      ) : null}

      {activeView === "registry" ? (
        <section className="app-default-card extensions-view" aria-labelledby="extensions-registry-heading">
          <div className="extensions-view__header">
            <h3 id="extensions-registry-heading">Registry</h3>
            {registry.length > 0
              ? <CoreUIBadge tone="info">{registry.length} available</CoreUIBadge>
              : registryDiagnostics.some((d) => d.severity === "error")
                ? <CoreUIBadge tone="error">unavailable</CoreUIBadge>
                : <CoreUIBadge tone="neutral">0 available</CoreUIBadge>
            }
          </div>
          {registry.length === 0 && registryDiagnostics.some((d) => d.severity === "error") && (
            <div className="coreui-panel-note coreui-panel-note--error" role="alert">
              GitHub registry unavailable. Check your network connection and click Refresh to retry.
            </div>
          )}
          <div className="extensions-cards">
            {registry.map((item) => {
              const installedItem = installedById.get(item.id);
              const isBusy = busyId === item.id || dockerUpdateBusy === item.id || dockerUpdateBusy === "__bulk__";
              return (
                <article
                  key={item.id}
                  className={`coreui-card-shell coreui-p-md extensions-card extensions-card--horizontal ${!installedItem ? "extensions-card--clickable" : ""}`}
                  onClick={() => openDetails(item)}
                >
                  <div className="extensions-card__main">
                    <div className="extensions-card__identity">
                      <ExtensionIcon icon={item.icon} iconUrl={item.icon_url} />
                      <ExtensionCardCopy title={item.title || item.id} description={item.description} />
                    </div>
                    <div className="extensions-card__meta-row" aria-label="Extension metadata">
                      <CoreUIBadge tone="neutral">ID: {item.id}</CoreUIBadge>
                      <CoreUIBadge tone="neutral">{item.visibility || "trusted"}</CoreUIBadge>
                      {item.repository ? (
                        <CoreUIBadge tone="neutral">{item.repository_id || item.repository}</CoreUIBadge>
                      ) : null}
                    </div>
                    <div className="extensions-card__aside">
                      <CoreUIBadge>{item.latest_version || item.default_ref || "GitHub"}</CoreUIBadge>
                      <div className="extensions-card__actions">
                        {!installedItem ? (
                          <>
                            <CoreUIButton
                              variant="primary"
                              disabled={isBusy || detailsLoading}
                              onClick={(event) => {
                                event.stopPropagation();
                                openDetails(item);
                              }}
                            >
                              Details
                            </CoreUIButton>
                            {item.latest_version || item.default_ref ? (
                              <CoreUIButton
                                variant="ghost"
                                disabled={isBusy}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  runAction(item.id, (id) => installExtension(id), "install");
                                }}
                              >
                                Install
                              </CoreUIButton>
                            ) : null}
                          </>
                        ) : (
                          <>
                            {renderDockerUpdateButton(installedItem, { stopPropagation: true })}
                            <CoreUIButton
                              variant="danger"
                              disabled={isBusy}
                              onClick={(event) => {
                                event.stopPropagation();
                                runAction(item.id, (id) => removeExtension(id), "remove");
                              }}
                            >
                              Remove
                            </CoreUIButton>
                            {installedItem.enabled ? (
                              <CoreUIButton
                                variant="ghost"
                                disabled={isBusy}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  runAction(item.id, (id) => disableExtension(id), "disable");
                                }}
                              >
                                Disable
                              </CoreUIButton>
                            ) : (
                              <CoreUIButton
                                variant="primary"
                                disabled={isBusy}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  runAction(item.id, (id) => enableExtension(id), "enable");
                                }}
                              >
                                Enable
                              </CoreUIButton>
                            )}
                          </>
                        )}
                      </div>
                    </div>
                  </div>
                  <CapabilityList capabilities={item.capabilities} />
                </article>
              );
            })}
            {!registry.length && !registryLoading ? <div className="extensions-empty">No registry entries.</div> : null}
          </div>
        </section>
      ) : null}

      {activeView === "installed" ? (
        <section className="app-default-card extensions-view" aria-labelledby="extensions-installed-heading">
          <div className="extensions-view__header">
            <h3 id="extensions-installed-heading">Installed</h3>
            <div className="extensions-view__header-badges">
              <CoreUIBadge tone="info">{installed.length} installed</CoreUIBadge>
              {dockerExtensions.length > 0 ? (
                <CoreUIBadge tone="neutral">{dockerExtensions.length} with Docker</CoreUIBadge>
              ) : null}
              {dockerUpdatesAvailable.length > 0 ? (
                <CoreUIBadge tone="warning">{dockerUpdatesAvailable.length} update available</CoreUIBadge>
              ) : null}
            </div>
          </div>
          <div className="extensions-cards">
            {installed.map((item) => (
            <article key={item.id} className="coreui-card-shell coreui-p-md extensions-card extensions-card--horizontal installed-card">
              <div className="extensions-card__main">
                <div className="extensions-card__identity">
                  <ExtensionIcon icon={item.icon} iconUrl={item.icon_url} />
                  <ExtensionCardCopy title={item.title || item.id} description={item.description} />
                </div>
                <div className="extensions-card__meta-row" aria-label="Installed extension metadata">
                  <CoreUIBadge tone="neutral">v{item.version}</CoreUIBadge>
                  {item.provenance?.selected_ref && item.provenance.selected_ref !== item.version ? (
                    <CoreUIBadge tone="neutral">Ref: {item.provenance.selected_ref}</CoreUIBadge>
                  ) : null}
                  <CoreUIBadge tone={item.enabled ? "success" : "neutral"}>
                    {item.enabled ? "Enabled" : "Disabled"}
                  </CoreUIBadge>
                  {item.sandboxed ? (
                    <CoreUIBadge tone={item.sandbox_blocked ? "warning" : "info"}>
                      Sandbox: {item.sandbox_status || "ready"}
                    </CoreUIBadge>
                  ) : null}
                  {item.restart_required ? <CoreUIBadge tone="warning">Restart required</CoreUIBadge> : null}
                  {item.security_blocked ? <CoreUIBadge tone="error">Security blocked</CoreUIBadge> : null}
                  {item.sandbox_blocked ? <CoreUIBadge tone="warning">Manual restart required</CoreUIBadge> : null}
                  {dockerUpdateAvailable(item) ? <CoreUIBadge tone="warning">New version</CoreUIBadge> : null}
                  {hasDockerContainer(item) && item.docker?.image ? (
                    <CoreUIBadge
                      tone={dockerUpdateAvailable(item) ? "warning" : "neutral"}
                      title={[
                        item.docker.image,
                        item.docker.current_version ? `Current: ${item.docker.current_version}` : "",
                        item.docker.update_version && dockerUpdateAvailable(item)
                          ? `Update: ${item.docker.update_version}`
                          : "",
                        item.docker.update_message || "",
                      ]
                        .filter(Boolean)
                        .join(" · ")}
                    >
                      {formatDockerVersionLabel(item.docker)}
                    </CoreUIBadge>
                  ) : null}
                </div>
                <div className="extensions-card__aside">
                  <HealthPill health={{ status: item.status || "installed" }} />
                  <div className="extensions-card__actions">
                    {renderDockerUpdateButton(item)}
                    <CoreUIButton
                      variant="danger"
                      disabled={busyId === item.id || dockerUpdateBusy === item.id || dockerUpdateBusy === "__bulk__"}
                      onClick={() => runAction(item.id, (id) => removeExtension(id), "remove")}
                    >
                      Remove
                    </CoreUIButton>
                    {item.enabled ? (
                      <CoreUIButton
                        variant="ghost"
                        disabled={busyId === item.id || dockerUpdateBusy === item.id || dockerUpdateBusy === "__bulk__"}
                        onClick={() => runAction(item.id, (id) => disableExtension(id), "disable")}
                      >
                        Disable
                      </CoreUIButton>
                    ) : (
                      <CoreUIButton
                        variant="primary"
                        disabled={busyId === item.id || dockerUpdateBusy === item.id || dockerUpdateBusy === "__bulk__"}
                        onClick={() => runAction(item.id, (id) => enableExtension(id), "enable")}
                      >
                        Enable
                      </CoreUIButton>
                    )}
                  </div>
                </div>
              </div>
              {item.error ? <pre className="extensions-card__error extensions-card__details">{item.error}</pre> : null}
              <SandboxDiagnostics item={item} busyId={busyId || dockerUpdateBusy} runAction={runAction} />
              <SecurityFindings findings={item.security_findings} />
            </article>
            ))}
            {!installed.length && !loading ? <div className="extensions-empty">No installed extensions.</div> : null}
          </div>
        </section>
      ) : null}

      {activeView === "providers" ? (
        <section className="app-default-card extensions-view" aria-labelledby="extensions-providers-heading">
          <div className="extensions-view__header">
            <h3 id="extensions-providers-heading">Providers</h3>
            <CoreUIBadge tone="info">{providers.length} loaded</CoreUIBadge>
          </div>
          <div className="extensions-cards">
            {providers.map((provider) => (
            <article key={provider.provider_id} className="coreui-card-shell coreui-p-md extensions-card extensions-card--horizontal provider-card">
              <div className="extensions-card__main">
                <div className="extensions-card__identity">
                  <span className="material-symbols-outlined extensions-card__icon" aria-hidden="true">
                    hub
                  </span>
                  <ExtensionCardCopy title={provider.title} description={provider.description} />
                </div>
                <div className="extensions-card__meta-row" aria-label="Provider metadata">
                  <CoreUIBadge tone="neutral">{provider.provider_id}</CoreUIBadge>
                  <CoreUIBadge tone="neutral">{provider.extension_id}</CoreUIBadge>
                  <CoreUIBadge tone="info">{(provider.models || []).length} models</CoreUIBadge>
                </div>
                <div className="extensions-card__aside">
                  <HealthPill health={provider.health} />
                </div>
              </div>
            </article>
            ))}
            {!providers.length && !loading ? <div className="extensions-empty">No loaded providers.</div> : null}
          </div>
        </section>
      ) : null}

      <ExtensionDetailsModal
        details={details}
        selectedRef={selectedRef}
        setSelectedRef={setSelectedRef}
        manualRef={manualRef}
        setManualRef={setManualRef}
        busy={Boolean(busyId)}
        onInstall={installFromDetails}
        onClose={() => setDetails(null)}
      />
    </div>
  );
}
