import { useCallback, useEffect, useMemo, useState } from "react";

import CoreUIBadge from "./CoreUIBadge";
import CoreUIButton from "./CoreUIButton";
import CoreUIPillTabs from "./CoreUIPillTabs";
import {
  disableExtension,
  enableExtension,
  getExtensionInstalled,
  getExtensionProviders,
  getExtensionRegistry,
  getExtensionUiPayload,
  installExtension,
  removeExtension,
} from "../services/api";
import "../styles/components/ExtensionsTab.css";

const EXTENSION_VIEWS = [
  { id: "registry", label: "Registry" },
  { id: "installed", label: "Installed" },
  { id: "providers", label: "Providers" },
];

function ExtensionIcon({ icon, iconUrl }) {
  const url = String(iconUrl || "").trim();
  const [imageFailed, setImageFailed] = useState(false);

  useEffect(() => {
    setImageFailed(false);
  }, [url]);

  if (url && !imageFailed) {
    const isSvg = url.toLowerCase().endsWith(".svg") || url.toLowerCase().includes(".svg?");
    if (isSvg) {
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

function SecurityFindings({ findings }) {
  const rows = Array.isArray(findings) ? findings : [];
  if (!rows.length) return null;
  return (
    <div className="extensions-security-findings">
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

export default function ExtensionsTab({ onErrorStateChange }) {
  const [activeView, setActiveView] = useState("registry");
  const [registry, setRegistry] = useState([]);
  const [installed, setInstalled] = useState([]);
  const [providers, setProviders] = useState([]);
  const [uiPayload, setUiPayload] = useState({ extensions: [], failed: [] });
  const [busyId, setBusyId] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [registryData, installedData, providersData, uiData] = await Promise.all([
        getExtensionRegistry(),
        getExtensionInstalled(),
        getExtensionProviders(),
        getExtensionUiPayload(),
      ]);
      setRegistry(registryData.registry || []);
      setInstalled(installedData.extensions || []);
      setProviders(providersData.providers || []);
      setUiPayload({ extensions: uiData.extensions || [], failed: uiData.failed || [] });
      onErrorStateChange?.(false);
    } catch (e) {
      const msg = String(e?.message || e || "Failed to load extensions");
      setError(msg);
      onErrorStateChange?.(true);
    } finally {
      setLoading(false);
    }
  }, [onErrorStateChange]);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const installedById = useMemo(
    () => new Map(installed.map((item) => [item.id, item])),
    [installed]
  );
  const providerByExtensionId = useMemo(
    () => new Map(providers.map((item) => [item.extension_id, item])),
    [providers]
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
    async (extensionId, fn) => {
      setBusyId(extensionId);
      setError("");
      try {
        await fn(extensionId);
        await loadAll();
        onErrorStateChange?.(false);
      } catch (e) {
        const msg = String(e?.message || e || "Action failed");
        setError(msg);
        onErrorStateChange?.(true);
      } finally {
        setBusyId("");
      }
    },
    [loadAll, onErrorStateChange]
  );

  return (
    <div className="extensions-tab tab-view">
      <div className="extensions-tab__header">
        <div>
          <h2>Extensions</h2>
          <p>Trusted registry, installed providers, and declarative CoreUI schemas.</p>
        </div>
        <CoreUIButton variant="primary" onClick={loadAll} disabled={loading || Boolean(busyId)}>
          Refresh
        </CoreUIButton>
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

      {activeView === "registry" ? (
        <section className="app-default-card extensions-view" aria-labelledby="extensions-registry-heading">
          <div className="extensions-view__header">
            <h3 id="extensions-registry-heading">Registry</h3>
            <CoreUIBadge tone="info">{registry.length} available</CoreUIBadge>
          </div>
          <div className="extensions-cards">
            {registry.map((item) => {
              const installedItem = installedById.get(item.id);
              const isBusy = busyId === item.id;
              return (
                <article key={item.id} className="coreui-card-shell coreui-p-md extensions-card">
                  <div className="extensions-card__head">
                    <div className="extensions-card__title-row">
                      <ExtensionIcon icon={item.icon} iconUrl={item.icon_url} />
                      <div>
                        <h4>{item.title || item.id}</h4>
                        <p>{item.description || "No description."}</p>
                      </div>
                    </div>
                    <CoreUIBadge>{item.latest_version || item.default_ref || "latest"}</CoreUIBadge>
                  </div>
                  <div className="extensions-card__meta">
                    <span>ID: {item.id}</span>
                    <span>Visibility: {item.visibility || "trusted"}</span>
                  </div>
                  <div className="extensions-card__actions">
                    {!installedItem ? (
                      <CoreUIButton
                        variant="primary"
                        disabled={isBusy}
                        onClick={() => runAction(item.id, (id) => installExtension(id))}
                      >
                        Install
                      </CoreUIButton>
                    ) : (
                      <>
                        <CoreUIButton
                          variant="danger"
                          disabled={isBusy}
                          onClick={() => runAction(item.id, (id) => removeExtension(id))}
                        >
                          Remove
                        </CoreUIButton>
                        {installedItem.enabled ? (
                          <CoreUIButton
                            variant="ghost"
                            disabled={isBusy}
                            onClick={() => runAction(item.id, (id) => disableExtension(id))}
                          >
                            Disable
                          </CoreUIButton>
                        ) : (
                          <CoreUIButton
                            variant="primary"
                            disabled={isBusy}
                            onClick={() => runAction(item.id, (id) => enableExtension(id))}
                          >
                            Enable
                          </CoreUIButton>
                        )}
                      </>
                    )}
                  </div>
                </article>
              );
            })}
            {!registry.length && !loading ? <div className="extensions-empty">No registry entries.</div> : null}
          </div>
        </section>
      ) : null}

      {activeView === "installed" ? (
        <section className="app-default-card extensions-view" aria-labelledby="extensions-installed-heading">
          <div className="extensions-view__header">
            <h3 id="extensions-installed-heading">Installed</h3>
            <CoreUIBadge tone="info">{installed.length} installed</CoreUIBadge>
          </div>
          <div className="extensions-cards">
            {installed.map((item) => (
            <article key={item.id} className="coreui-card-shell coreui-p-md extensions-card installed-card">
              <div className="extensions-card__head">
                <div className="extensions-card__title-row">
                  <ExtensionIcon icon={item.icon} iconUrl={item.icon_url} />
                  <div>
                    <h4>{item.title || item.id}</h4>
                    <p>{item.description || "No description."}</p>
                  </div>
                </div>
                <HealthPill health={{ status: item.status || "installed" }} />
              </div>
              <div className="extensions-card__meta">
                <span>Version: {item.version}</span>
                <span>Enabled: {String(Boolean(item.enabled))}</span>
                {item.restart_required ? <span>Restart required</span> : null}
                {item.security_blocked ? <span>Security blocked</span> : null}
              </div>
              {item.error ? <pre className="extensions-card__error">{item.error}</pre> : null}
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
            <article key={provider.provider_id} className="coreui-card-shell coreui-p-md extensions-card provider-card">
              <div className="extensions-card__head">
                <div>
                  <h4>{provider.title}</h4>
                  <p>{provider.description || "No description."}</p>
                </div>
                <HealthPill health={provider.health} />
              </div>
              <div className="extensions-card__meta">
                <span>Provider: {provider.provider_id}</span>
                <span>Extension: {provider.extension_id}</span>
                <span>Models: {(provider.models || []).length}</span>
              </div>
            </article>
            ))}
            {!providers.length && !loading ? <div className="extensions-empty">No loaded providers.</div> : null}
          </div>
        </section>
      ) : null}
    </div>
  );
}
