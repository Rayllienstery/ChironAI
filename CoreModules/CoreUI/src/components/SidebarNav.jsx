import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import Card from "./Card";

const LS_WIDTH = "coreui.sidebar.width";
const LS_COLLAPSED = "coreui.sidebar.collapsed";
const MIN_WIDTH = 200;
const MAX_WIDTH = 360;
const DEFAULT_WIDTH = 260;

function readStoredWidth() {
  try {
    const v = parseInt(localStorage.getItem(LS_WIDTH) || "", 10);
    if (Number.isFinite(v) && v >= MIN_WIDTH && v <= MAX_WIDTH) return v;
  } catch {
    /* ignore */
  }
  return DEFAULT_WIDTH;
}

function readStoredCollapsed() {
  try {
    return localStorage.getItem(LS_COLLAPSED) === "1";
  } catch {
    return false;
  }
}

/** Material Symbols ligature names (Google Fonts) */
const TAB_MATERIAL_ICONS = {
  dashboard: "dashboard",
  "llm-proxy": "smart_toy",
  "claw-proxy": "terminal",
  logs: "article",
  rag: "database",
  crawler: "travel_explore",
  "template-editor": "edit_note",
  testing: "science",
};

function TabIcon({ tabId }) {
  const ligature = TAB_MATERIAL_ICONS[tabId] ?? "widgets";
  return (
    <span className="material-symbols-outlined coreui-sidebar__icon" aria-hidden="true">
      {ligature}
    </span>
  );
}

function ServiceStartStopButton({ running, disabled, startLabel, stopLabel, onAction }) {
  const label = running ? stopLabel : startLabel;
  return (
    <button
      type="button"
      className="coreui-sidebar__service-btn"
      disabled={disabled}
      title={label}
      aria-label={label}
      onClick={onAction}
    >
      <span
        className="material-symbols-outlined coreui-sidebar__service-btn-icon coreui-sidebar__service-btn-icon--filled"
        aria-hidden="true"
      >
        {running ? "stop" : "play_arrow"}
      </span>
    </button>
  );
}

function ServiceOpenResourceButton({ disabled, label, onOpen }) {
  return (
    <button
      type="button"
      className="coreui-sidebar__service-btn"
      disabled={disabled}
      title={label}
      aria-label={label}
      onClick={onOpen}
    >
      <span
        className="material-symbols-outlined coreui-sidebar__service-btn-icon"
        aria-hidden="true"
      >
        open_in_new
      </span>
    </button>
  );
}

function CollapseIcon({ expanded }) {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {expanded ? (
        <path d="M14 6 8 12l6 6" />
      ) : (
        <path d="M10 6l6 6-6 6" />
      )}
    </svg>
  );
}

/**
 * @param {{
 *   tabs: { id: string, label: string }[],
 *   activeTab: string,
 *   onTabChange: (id: string) => void,
 *   tabErrors?: Record<string, boolean>,
 *   onSettings?: () => void,
 *   onStopWebUi?: () => void,
 *   settingsActive?: boolean,
 *   ollamaStatus?: { running: boolean | null, url: string | null },
 *   ragStatus?: { running: boolean | null, url: string | null },
 *   openWebUiStatus?: { running: boolean | null, url: string | null },
 *   statusLoading?: boolean,
 *   statusBusy?: boolean,
 *   onOllamaStartStop?: (action: "start" | "stop") => void,
 *   onRagStartStop?: (action: "start" | "stop") => void,
 *   onOpenWebUiStartStop?: (action: "start" | "stop") => void,
 *   onOpenOllamaUI?: () => void,
 *   onOpenRagUI?: () => void,
 *   onOpenOpenWebUiUI?: () => void,
 * }} props
 */
function SidebarNav({
  tabs,
  activeTab,
  onTabChange,
  tabErrors,
  onSettings,
  onStopWebUi,
  settingsActive,
  ollamaStatus,
  ragStatus,
  openWebUiStatus,
  statusLoading = false,
  statusBusy = false,
  onOllamaStartStop,
  onRagStartStop,
  onOpenWebUiStartStop,
  onOpenOllamaUI,
  onOpenRagUI,
  onOpenOpenWebUiUI,
}) {
  const asideRef = useRef(null);
  const [collapsed, setCollapsed] = useState(readStoredCollapsed);
  const [expandedWidth, setExpandedWidth] = useState(readStoredWidth);
  const resizingRef = useRef(false);
  const dragStartRef = useRef({ x: 0, w: 0 });

  const syncAppChrome = useCallback(() => {
    const aside = asideRef.current;
    const app = aside?.closest(".app");
    if (!app) return;
    if (collapsed) {
      app.classList.add("app--sidebar-collapsed");
      app.style.setProperty(
        "--coreui-sidebar-width",
        "var(--coreui-sidebar-width-collapsed)",
      );
    } else {
      app.classList.remove("app--sidebar-collapsed");
      app.style.setProperty("--coreui-sidebar-width", `${expandedWidth}px`);
    }
  }, [collapsed, expandedWidth]);

  useLayoutEffect(() => {
    syncAppChrome();
  }, [syncAppChrome]);

  useEffect(() => {
    try {
      localStorage.setItem(LS_COLLAPSED, collapsed ? "1" : "0");
      localStorage.setItem(LS_WIDTH, String(expandedWidth));
    } catch {
      /* ignore */
    }
  }, [collapsed, expandedWidth]);

  const toggleCollapsed = () => setCollapsed((c) => !c);

  const onResizePointerDown = (e) => {
    if (collapsed) return;
    e.preventDefault();
    resizingRef.current = true;
    const aside = asideRef.current;
    if (!aside) return;
    dragStartRef.current = {
      x: e.clientX,
      w: aside.getBoundingClientRect().width,
    };
    document.body.classList.add("coreui-resizing");

    const onMove = (ev) => {
      if (!resizingRef.current) return;
      const { x, w } = dragStartRef.current;
      const next = Math.round(
        Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, w + (ev.clientX - x))),
      );
      const app = aside.closest(".app");
      if (app) app.style.setProperty("--coreui-sidebar-width", `${next}px`);
    };

    const onUp = () => {
      resizingRef.current = false;
      document.body.classList.remove("coreui-resizing");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      const asideEl = asideRef.current;
      const app = asideEl?.closest(".app");
      if (asideEl && app) {
        const w = asideEl.getBoundingClientRect().width;
        const clamped = Math.min(
          MAX_WIDTH,
          Math.max(MIN_WIDTH, Math.round(w)),
        );
        setExpandedWidth(clamped);
        app.style.setProperty("--coreui-sidebar-width", `${clamped}px`);
      }
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };

  return (
    <aside
      ref={asideRef}
      className="coreui-sidebar"
      aria-label="Main navigation"
    >
      <div className="coreui-sidebar__header">
        <div className="coreui-sidebar__brand">
          <div className="coreui-sidebar__logo" aria-hidden="true">
            C
          </div>
          <span className="coreui-sidebar__title">ChironAI</span>
        </div>
        <button
          type="button"
          className="coreui-sidebar__collapse"
          onClick={toggleCollapsed}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          <CollapseIcon expanded={!collapsed} />
        </button>
      </div>
      <div className="coreui-sidebar__content">
        <nav className="coreui-sidebar__nav">
          {tabs.map((tab) => {
            const active = activeTab === tab.id;
            const hasError = Boolean(tabErrors && tabErrors[tab.id]);
            return (
              <button
                key={tab.id}
                type="button"
                className={`coreui-sidebar__link${active ? " coreui-sidebar__link--active" : ""}`}
                onClick={() => onTabChange(tab.id)}
                aria-current={active ? "page" : undefined}
                title={collapsed ? tab.label : undefined}
              >
                <TabIcon tabId={tab.id} />
                <span className="coreui-sidebar__link-label">{tab.label}</span>
                {hasError && (
                  <span className="coreui-sidebar__badge" aria-label="Error">
                    !
                  </span>
                )}
              </button>
            );
          })}
        </nav>
        <div
          className="coreui-sidebar__services"
          aria-label="Services status"
        >
          <div className="coreui-sidebar__service-item">
            <span
              className={`coreui-sidebar__service-dot ${statusLoading ? "updating" : ollamaStatus?.running ? "running" : "stopped"}`}
            />
            <span className="coreui-sidebar__service-label">Ollama</span>
            <div className="coreui-sidebar__service-actions">
              <ServiceStartStopButton
                running={Boolean(ollamaStatus?.running)}
                disabled={statusBusy || statusLoading}
                startLabel="Start Ollama"
                stopLabel="Stop Ollama"
                onAction={() =>
                  onOllamaStartStop?.(ollamaStatus?.running ? "stop" : "start")}
              />
              <ServiceOpenResourceButton
                disabled={
                  statusBusy ||
                  statusLoading ||
                  !ollamaStatus?.running ||
                  !ollamaStatus?.url
                }
                label="Open Ollama UI"
                onOpen={() => onOpenOllamaUI?.()}
              />
            </div>
          </div>
          <div className="coreui-sidebar__service-item">
            <span
              className={`coreui-sidebar__service-dot ${statusLoading ? "updating" : ragStatus?.running ? "running" : "stopped"}`}
            />
            <span className="coreui-sidebar__service-label">RAG / Qdrant</span>
            <div className="coreui-sidebar__service-actions">
              <ServiceStartStopButton
                running={Boolean(ragStatus?.running)}
                disabled={statusBusy || statusLoading}
                startLabel="Start RAG / Qdrant"
                stopLabel="Stop RAG / Qdrant"
                onAction={() =>
                  onRagStartStop?.(ragStatus?.running ? "stop" : "start")}
              />
              <ServiceOpenResourceButton
                disabled={
                  statusBusy ||
                  statusLoading ||
                  !ragStatus?.running ||
                  !ragStatus?.url
                }
                label="Open RAG / Qdrant UI"
                onOpen={() => onOpenRagUI?.()}
              />
            </div>
          </div>
          <div className="coreui-sidebar__service-item">
            <span
              className={`coreui-sidebar__service-dot ${statusLoading ? "updating" : openWebUiStatus?.running ? "running" : "stopped"}`}
            />
            <span className="coreui-sidebar__service-label">Open WebUI</span>
            <div className="coreui-sidebar__service-actions">
              <ServiceStartStopButton
                running={Boolean(openWebUiStatus?.running)}
                disabled={statusBusy || statusLoading}
                startLabel="Start Open WebUI"
                stopLabel="Stop Open WebUI"
                onAction={() =>
                  onOpenWebUiStartStop?.(
                    openWebUiStatus?.running ? "stop" : "start",
                  )}
              />
              <ServiceOpenResourceButton
                disabled={
                  statusBusy ||
                  statusLoading ||
                  !openWebUiStatus?.running ||
                  !openWebUiStatus?.url
                }
                label="Open Open WebUI"
                onOpen={() => onOpenOpenWebUiUI?.()}
              />
            </div>
          </div>
        </div>
        <div className="coreui-sidebar__dock">
          {(onSettings || onStopWebUi) && (
            <footer className="coreui-sidebar__footer">
              {onSettings && (
                <Card
                  as="button"
                  type="button"
                  className={`coreui-sidebar__footer-btn coreui-sidebar__footer-btn--settings${settingsActive ? " coreui-sidebar__footer-btn--active" : ""}`}
                  onClick={onSettings}
                  title="Settings"
                  aria-current={settingsActive ? "page" : undefined}
                >
                  <span
                    className="material-symbols-outlined coreui-sidebar__footer-icon"
                    aria-hidden="true"
                  >
                    settings
                  </span>
                  <span className="coreui-sidebar__footer-label">Settings</span>
                </Card>
              )}
              {onStopWebUi && (
                <Card
                  as="button"
                  type="button"
                  className="coreui-sidebar__footer-btn coreui-sidebar__footer-btn--stop"
                  onClick={onStopWebUi}
                  title="Stop WebUI server"
                >
                  <span
                    className="material-symbols-outlined coreui-sidebar__footer-icon"
                    aria-hidden="true"
                  >
                    power
                  </span>
                  <span className="coreui-sidebar__footer-label">Stop WebUI</span>
                </Card>
              )}
            </footer>
          )}
        </div>
      </div>
      <div
        className="coreui-sidebar__resize"
        role="separator"
        aria-orientation="vertical"
        aria-hidden={collapsed}
        onPointerDown={onResizePointerDown}
        title="Drag to resize"
      />
    </aside>
  );
}

export default SidebarNav;
