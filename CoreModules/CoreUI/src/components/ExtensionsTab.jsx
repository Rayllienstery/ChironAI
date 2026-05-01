import { useCallback, useEffect, useMemo, useState } from "react";

import Card from "./Card";
import CoreUIButton from "./CoreUIButton";
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

function HealthPill({ health }) {
  const status = String(health?.status || "unknown");
  return <span className={`extensions-health-pill status-${status}`}>{status}</span>;
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
                <Card key={section.id || section.title} className="extensions-schema-section">
                  <div className="extensions-schema-section-header">
                    <h4>{section.title || "Section"}</h4>
                  </div>
                  <div className="extensions-schema-section-body">
                    {(Array.isArray(section.components) ? section.components : []).map((component) =>
                      renderComponent(component, page.extensionId)
                    )}
                  </div>
                </Card>
              ))
            : null}
        </div>
      ))}
    </div>
  );
}

export default function ExtensionsTab({ onErrorStateChange }) {
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
          <p>Trusted extension registry, installed providers, and declarative CoreUI schemas.</p>
        </div>
        <CoreUIButton variant="primary" onClick={loadAll} disabled={loading || Boolean(busyId)}>
          Refresh
        </CoreUIButton>
      </div>

      {error ? <Card className="extensions-error">{error}</Card> : null}

      <Card className="extensions-grid-card">
        <div className="extensions-grid-card__header">
          <h3>Registry</h3>
          <span>{registry.length} available</span>
        </div>
        <div className="extensions-cards">
          {registry.map((item) => {
            const installedItem = installedById.get(item.id);
            const isBusy = busyId === item.id;
            return (
              <Card key={item.id} className="extensions-card">
                <div className="extensions-card__head">
                  <div>
                    <h4>{item.title || item.id}</h4>
                    <p>{item.description || "No description."}</p>
                  </div>
                  <span className="extensions-card__version">{item.latest_version || item.default_ref || ""}</span>
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
              </Card>
            );
          })}
        </div>
      </Card>

      <Card className="extensions-grid-card">
        <div className="extensions-grid-card__header">
          <h3>Installed</h3>
          <span>{installed.length} installed</span>
        </div>
        <div className="extensions-cards">
          {installed.map((item) => (
            <Card key={item.id} className="extensions-card installed-card">
              <div className="extensions-card__head">
                <div>
                  <h4>{item.title || item.id}</h4>
                  <p>{item.description || "No description."}</p>
                </div>
                <HealthPill health={{ status: item.status || "installed" }} />
              </div>
              <div className="extensions-card__meta">
                <span>Version: {item.version}</span>
                <span>Enabled: {String(Boolean(item.enabled))}</span>
                {item.restart_required ? <span>Restart required</span> : null}
              </div>
              {item.error ? <pre className="extensions-card__error">{item.error}</pre> : null}
            </Card>
          ))}
        </div>
      </Card>

      <Card className="extensions-grid-card">
        <div className="extensions-grid-card__header">
          <h3>Providers</h3>
          <span>{providers.length} loaded</span>
        </div>
        <div className="extensions-cards">
          {providers.map((provider) => (
            <Card key={provider.provider_id} className="extensions-card provider-card">
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
            </Card>
          ))}
        </div>
      </Card>

      <div className="extensions-ui">
        {(uiPayload.extensions || []).map((entry) => {
          const schemaWithExtensionIds = {
            ...entry.ui_schema,
            pages: Array.isArray(entry.ui_schema?.pages)
              ? entry.ui_schema.pages.map((page) => ({ ...page, extensionId: entry.id }))
              : [],
          };
          return (
            <Card key={entry.id} className="extensions-ui-card">
              <div className="extensions-grid-card__header">
                <h3>{entry.title}</h3>
                <span>{entry.id}</span>
              </div>
              <SchemaRenderer
                schema={schemaWithExtensionIds}
                providerByExtensionId={providerByExtensionId}
              />
            </Card>
          );
        })}
      </div>

      {Array.isArray(uiPayload.failed) && uiPayload.failed.length ? (
        <Card className="extensions-grid-card">
          <div className="extensions-grid-card__header">
            <h3>Failed Extensions</h3>
            <span>{uiPayload.failed.length}</span>
          </div>
          <div className="extensions-failed-list">
            {uiPayload.failed.map((item) => (
              <pre key={item.id} className="extensions-card__error">
                {item.id}: {item.error}
              </pre>
            ))}
          </div>
        </Card>
      ) : null}
    </div>
  );
}
