import { useCallback, useEffect, useMemo, useState, useRef } from "react";

import CoreUIBadge from "./CoreUIBadge";
import CoreUIButton from "./CoreUIButton";
import CoreUIPillTabs from "./CoreUIPillTabs";
import {
  checkDockerImageUpdate,
  getDockerContainers,
  getDockerImages,
  getDockerStatus,
  removeDockerContainer,
  removeDockerImage,
  startDockerContainer,
  stopDockerContainer,
  updateDockerImage,
} from "../services/api";
import "../styles/components/DockerTab.css";

const VIEWS = [
  { id: "containers", label: "Containers" },
  { id: "images", label: "Images" },
  { id: "contracts", label: "Contracts" },
];

function icon(name) {
  return <span className="material-symbols-outlined" aria-hidden="true">{name}</span>;
}

function shortId(value) {
  const text = String(value || "");
  return text.replace(/^sha256:/, "").slice(0, 12) || "";
}

function statusTone(status) {
  const s = String(status || "").toLowerCase();
  if (s === "up_to_date" || s === "running" || s.includes("ready")) return "success";
  if (s === "update_available" || s === "unknown") return "warning";
  if (s === "not_local" || s === "error" || s.includes("not")) return "error";
  return "neutral";
}

function Message({ value }) {
  if (!value) return null;
  const tone = value.type === "error" ? "error" : "info";
  return <div className={`docker-message docker-message--${tone}`}>{value.text}</div>;
}

function DockerActionMenu({ id, container, imageName, busyKey, runAction, onCheckUpdate, onUpdateImage }) {
  const [open, setOpen] = useState(false);
  const [menuStyle, setMenuStyle] = useState({});
  const rootRef = useRef(null);

  const toggleOpen = () => {
    if (!open && rootRef.current) {
      const rect = rootRef.current.getBoundingClientRect();
      setMenuStyle({
        position: "fixed",
        top: `${rect.bottom + 4}px`,
        right: `${window.innerWidth - rect.right}px`,
        zIndex: 1000,
      });
    }
    setOpen(!open);
  };

  useEffect(() => {
    if (!open) return;
    const handleDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    const handleKey = (e) => {
      if (e.key === "Escape") setOpen(false);
    };
    const handleScroll = () => setOpen(false);

    window.addEventListener("pointerdown", handleDown);
    window.addEventListener("keydown", handleKey);
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      window.removeEventListener("pointerdown", handleDown);
      window.removeEventListener("keydown", handleKey);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [open]);

  const busy = busyKey.includes(String(id || imageName));

  return (
    <div className="docker-action-menu-root" ref={rootRef}>
      <button
        type="button"
        className="docker-action-menu-trigger"
        onClick={toggleOpen}
        aria-haspopup="menu"
        aria-expanded={open}
        title="Actions"
      >
        {icon("more_vert")}
      </button>
      {open && (
        <div className="docker-action-menu" role="menu" style={menuStyle}>
          {container && (
            <>
              {container.running ? (
                <button
                  type="button"
                  role="menuitem"
                  disabled={busy || Boolean(busyKey)}
                  onClick={() => {
                    setOpen(false);
                    runAction(`stop:${id}`, () => stopDockerContainer(id), `Stopped ${id}`);
                  }}
                >
                  {icon("stop_circle")}
                  <span>Stop</span>
                </button>
              ) : (
                <button
                  type="button"
                  role="menuitem"
                  disabled={busy || Boolean(busyKey)}
                  onClick={() => {
                    setOpen(false);
                    runAction(`start:${id}`, () => startDockerContainer(id), `Started ${id}`);
                  }}
                >
                  {icon("play_circle")}
                  <span>Start</span>
                </button>
              )}
              <button
                type="button"
                role="menuitem"
                className="docker-action-menu-item--danger"
                disabled={busy || Boolean(busyKey)}
                onClick={() => {
                  setOpen(false);
                  if (window.confirm(`Remove container ${id}?`)) {
                    runAction(`remove:${id}`, () => removeDockerContainer(id), `Removed ${id}`);
                  }
                }}
              >
                {icon("delete")}
                <span>Remove</span>
              </button>
            </>
          )}
          {imageName && (
            <>
              <button
                type="button"
                role="menuitem"
                disabled={busy || Boolean(busyKey)}
                onClick={() => {
                  setOpen(false);
                  onCheckUpdate(imageName);
                }}
              >
                {icon("published_with_changes")}
                <span>Check update</span>
              </button>
              <button
                type="button"
                role="menuitem"
                disabled={busy || Boolean(busyKey)}
                onClick={() => {
                  setOpen(false);
                  onUpdateImage(imageName);
                }}
              >
                {icon("system_update_alt")}
                <span>Pull latest</span>
              </button>
              <button
                type="button"
                role="menuitem"
                className="docker-action-menu-item--danger"
                disabled={busy || Boolean(busyKey)}
                onClick={() => {
                  setOpen(false);
                  if (window.confirm(`Remove image ${imageName}?`)) {
                    runAction(`remove-image:${imageName}`, () => removeDockerImage(imageName), `Removed ${imageName}`);
                  }
                }}
              >
                {icon("delete")}
                <span>Remove</span>
              </button>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Docker management tab backed by the DockerManager host capability.
 * Lists containers and images, supports start/stop/restart, and shows
 * the live state of extension-owned services.
 */
export default function DockerTab() {
  const [activeView, setActiveView] = useState("containers");
  const [status, setStatus] = useState(null);
  const [containers, setContainers] = useState([]);
  const [images, setImages] = useState([]);
  const [busyKey, setBusyKey] = useState("");
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState(null);
  const [updateStatusByImage, setUpdateStatusByImage] = useState({});

  const loadAll = useCallback(async () => {
    setLoading(true);
    setMessage(null);
    try {
      const [statusData, containerData, imageData] = await Promise.all([
        getDockerStatus(),
        getDockerContainers(),
        getDockerImages(),
      ]);
      setStatus(statusData);
      setContainers(containerData.containers || []);
      setImages(imageData.images || []);
    } catch (e) {
      setMessage({ type: "error", text: String(e?.message || e || "Failed to load Docker state") });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadAll();
  }, [loadAll]);

  const viewTabs = useMemo(
    () =>
      VIEWS.map((view) => ({
        ...view,
        count:
          view.id === "containers"
            ? containers.length
            : view.id === "images"
              ? images.length
              : 0,
      })),
    [containers.length, images.length]
  );

  const runAction = useCallback(
    async (key, fn, successText, options = {}) => {
      setBusyKey(key);
      setMessage(null);
      try {
        const result = await fn();
        setMessage({ type: "info", text: successText || result.message || "Done" });
        if (options.refresh !== false) {
          await loadAll();
        }
        return result;
      } catch (e) {
        setMessage({ type: "error", text: String(e?.message || e || "Docker action failed") });
        return null;
      } finally {
        setBusyKey("");
      }
    },
    [loadAll]
  );

  const onCheckUpdate = useCallback(
    async (image) => {
      const result = await runAction(
        `check:${image}`,
        () => checkDockerImageUpdate(image),
        `Checked ${image}`,
        { refresh: false }
      );
      if (result) {
        setUpdateStatusByImage((prev) => ({ ...prev, [image]: result }));
      }
    },
    [runAction]
  );

  const onUpdateImage = useCallback(
    async (image) => {
      await runAction(`update:${image}`, () => updateDockerImage(image), `Updated ${image}`);
      setUpdateStatusByImage((prev) => {
        const next = { ...prev };
        delete next[image];
        return next;
      });
    },
    [runAction]
  );

  const statusBadge = status?.engine_ready
    ? <CoreUIBadge tone="success">Engine ready</CoreUIBadge>
    : status?.cli_available
      ? <CoreUIBadge tone="warning">Engine offline</CoreUIBadge>
      : <CoreUIBadge tone="error">CLI missing</CoreUIBadge>;

  return (
    <div className="docker-tab tab-view">
      <div className="docker-tab__header">
        <div>
          <h2>Docker</h2>
          <p>Inspect Docker Engine, local containers, and images from CoreUI.</p>
        </div>
        <CoreUIButton variant="primary" onClick={loadAll} disabled={loading || Boolean(busyKey)}>
          {icon("refresh")}
          Refresh
        </CoreUIButton>
      </div>

      <section className="app-default-card docker-status-panel" aria-label="Docker status">
        <div className="docker-status-main">
          {statusBadge}
          <div>
            <strong>{status?.docker_exe || "docker"}</strong>
            <span>{status?.error || "Docker CLI and Engine status loaded."}</span>
          </div>
        </div>
        <div className="docker-status-grid">
          <div>
            <span>CLI</span>
            <strong>{status?.cli_version || (status?.cli_available ? "available" : "not found")}</strong>
          </div>
          <div>
            <span>Server</span>
            <strong>{status?.server_version || (status?.engine_ready ? "ready" : "not ready")}</strong>
          </div>
          <div>
            <span>Containers</span>
            <strong>{containers.length}</strong>
          </div>
          <div>
            <span>Images</span>
            <strong>{images.length}</strong>
          </div>
        </div>
      </section>

      <CoreUIPillTabs
        tabs={viewTabs}
        value={activeView}
        onChange={setActiveView}
        ariaLabel="Docker views"
        getLabel={(tab) => (
          <span className="docker-view-tab-label">
            <span>{tab.label}</span>
            <CoreUIBadge>{tab.count}</CoreUIBadge>
          </span>
        )}
      />

      <Message value={message} />

      {activeView === "containers" ? (
        <section className="app-default-card docker-section" aria-labelledby="docker-containers-heading">
          <div className="docker-section__header">
            <h3 id="docker-containers-heading">Containers</h3>
            <CoreUIBadge tone="info">{containers.length} total</CoreUIBadge>
          </div>
          <div className="docker-table-wrap">
            <table className="docker-table">
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Image</th>
                  <th>Status</th>
                  <th>Ports</th>
                  <th>Created</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {containers.map((container) => {
                  const id = container.name || container.id;
                  const busy = busyKey.includes(String(id));
                  return (
                    <tr key={container.id || container.name}>
                      <td>
                        <strong>{container.name || shortId(container.id)}</strong>
                        <span>{shortId(container.id)}</span>
                      </td>
                      <td>{container.image}</td>
                      <td>
                        <CoreUIBadge tone={container.running ? "success" : "neutral"}>
                          {container.status || "stopped"}
                        </CoreUIBadge>
                      </td>
                      <td>{container.ports || ""}</td>
                      <td>{container.created || ""}</td>
                      <td>
                        <DockerActionMenu
                          id={id}
                          container={container}
                          busyKey={busyKey}
                          runAction={runAction}
                        />
                      </td>
                    </tr>
                  );
                })}
                {!containers.length && !loading ? (
                  <tr>
                    <td colSpan={6}>No containers found.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {activeView === "images" ? (
        <section className="app-default-card docker-section" aria-labelledby="docker-images-heading">
          <div className="docker-section__header">
            <h3 id="docker-images-heading">Images</h3>
            <CoreUIBadge tone="info">{images.length} local</CoreUIBadge>
          </div>
          <div className="docker-table-wrap">
            <table className="docker-table">
              <thead>
                <tr>
                  <th>Image</th>
                  <th>ID</th>
                  <th>Size</th>
                  <th>Created</th>
                  <th>Update</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {images.map((item) => {
                  const imageName = item.image || `${item.repository}:${item.tag}`;
                  const update = updateStatusByImage[imageName];
                  const busy = busyKey.includes(imageName);
                  return (
                    <tr key={`${item.id}:${imageName}`}>
                      <td>
                        <strong>{imageName}</strong>
                        <span>{item.repository}</span>
                      </td>
                      <td>{shortId(item.id)}</td>
                      <td>{item.size}</td>
                      <td>{item.created}</td>
                      <td>
                        {update ? (
                          <CoreUIBadge tone={statusTone(update.status)}>{update.status}</CoreUIBadge>
                        ) : (
                          <CoreUIBadge>not checked</CoreUIBadge>
                        )}
                      </td>
                      <td>
                        <DockerActionMenu
                          imageName={imageName}
                          busyKey={busyKey}
                          runAction={runAction}
                          onCheckUpdate={onCheckUpdate}
                          onUpdateImage={onUpdateImage}
                        />
                      </td>
                    </tr>
                  );
                })}
                {!images.length && !loading ? (
                  <tr>
                    <td colSpan={6}>No local images found.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {activeView === "contracts" ? (
        <section className="app-default-card docker-section docker-contracts" aria-labelledby="docker-contracts-heading">
          <div className="docker-section__header">
            <h3 id="docker-contracts-heading">Extension Contract</h3>
            <CoreUIBadge tone="info">CoreModule API</CoreUIBadge>
          </div>

          <div className="docker-contract-grid">
            <article className="docker-contract-block">
              <h4>Host capability</h4>
              <p>
                Extensions receive DockerManager through <code>host_context.docker_runtime</code>. They should not call
                CoreUI routes such as <code>/api/webui/docker/*</code>.
              </p>
              <pre>{`def create_provider(host_context, manifest):
    return MyProvider(host_context, manifest)

class MyProvider:
    def __init__(self, host_context, manifest):
        self._docker = host_context.docker_runtime
        self._manifest = manifest`}</pre>
            </article>

            <article className="docker-contract-block">
              <h4>Container spec</h4>
              <p>
                Use <code>DockerContainerSpec</code> for extension-owned containers. Ports and volumes are Docker
                CLI-compatible strings.
              </p>
              <pre>{`from docker_manager import DockerContainerSpec

spec = DockerContainerSpec(
    name="my-extension-service",
    image="ghcr.io/acme/my-service:latest",
    ports=["18080:8080"],
    env={"SERVICE_HOST": "0.0.0.0:8080"},
    volumes=["my_extension_data:/app/data"],
    labels={"chironai.extension": "my-extension"},
)`}</pre>
            </article>

            <article className="docker-contract-block">
              <h4>Lifecycle</h4>
              <p>
                <code>ensure_container</code> owns image pull, create, start, and recreate. Extension UI actions surface
                this processing through the standard extension action result state.
              </p>
              <pre>{`result = self._docker.ensure_container(spec)
if not result["ok"]:
    return {"ok": False, "message": result["error"]}

health = self._docker.wait_http(
    "http://localhost:18080",
    path="/health",
    timeout=60,
)`}</pre>
            </article>

            <article className="docker-contract-block">
              <h4>Actions</h4>
              <p>
                Service actions should use the contract directly. Do not import <code>api.http.service_control</code>
                from an Extension backend, and do not call <code>/api/webui/docker/*</code> from extension code.
              </p>
              <pre>{`def run_action(self, action_id, payload, *, runtime=None):
    if self._docker is None:
        return {"ok": False, "message": "Docker runtime is unavailable"}
    if action_id == "start_service":
        return self._docker.ensure_container(spec)
    if action_id == "stop_service":
        return self._docker.stop_container(spec.name)
    raise ValueError(f"Unsupported action: {action_id}")`}</pre>
            </article>
          </div>
        </section>
      ) : null}
    </div>
  );
}
