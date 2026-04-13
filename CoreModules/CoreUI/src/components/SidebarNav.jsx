import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import Card from "./Card";
import OllamaSidebarIcon from "./OllamaSidebarIcon";
import OpenWebUiSidebarIcon from "./OpenWebUiSidebarIcon";

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
  "rag-fusion-proxy": "psychology",
  "llm-proxy": "hub",
  logs: "article",
  rag: "database",
  crawler: "travel_explore",
  "template-editor": "edit_note",
  testing: "science",
};

function TabIcon({ tabId }) {
  if (tabId === "ollama") {
    return <OllamaSidebarIcon />;
  }
  if (tabId === "open-webui") {
    return <OpenWebUiSidebarIcon />;
  }
  const ligature = TAB_MATERIAL_ICONS[tabId] ?? "widgets";
  return (
    <span className="material-symbols-outlined coreui-sidebar__icon" aria-hidden="true">
      {ligature}
    </span>
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
            const isOllama = tab.id === "ollama";
            const isOpenWebUi = tab.id === "open-webui";
            const isRag = tab.id === "rag";
            return (
              <button
                key={tab.id}
                type="button"
                className={`coreui-sidebar__link${active ? " coreui-sidebar__link--active" : ""}${isOllama ? " coreui-sidebar__link--ollama" : ""}${isOpenWebUi ? " coreui-sidebar__link--openwebui" : ""}${isRag ? " coreui-sidebar__link--rag" : ""}`}
                onClick={() => onTabChange(tab.id)}
                aria-current={active ? "page" : undefined}
                title={collapsed ? tab.label : undefined}
              >
                <TabIcon tabId={tab.id} />
                <span className="coreui-sidebar__link-label">{tab.label}</span>
                {isOllama ? (
                  <span
                    className={`coreui-sidebar__service-dot coreui-sidebar__link-ollama-dot ${statusLoading ? "updating" : ollamaStatus?.running ? "running" : "stopped"}`}
                    aria-hidden="true"
                    title={
                      statusLoading
                        ? "Checking Ollama status…"
                        : ollamaStatus?.running
                          ? "Ollama reachable"
                          : "Ollama not reachable"
                    }
                  />
                ) : null}
                {isOpenWebUi ? (
                  <span
                    className={`coreui-sidebar__service-dot coreui-sidebar__link-openwebui-dot ${statusLoading ? "updating" : openWebUiStatus?.running ? "running" : "stopped"}`}
                    aria-hidden="true"
                    title={
                      statusLoading
                        ? "Checking Open WebUI status…"
                        : openWebUiStatus?.running
                          ? "Open WebUI running"
                          : "Open WebUI not running"
                    }
                  />
                ) : null}
                {isRag ? (
                  <span
                    className={`coreui-sidebar__service-dot coreui-sidebar__link-rag-dot ${statusLoading ? "updating" : ragStatus?.running ? "running" : "stopped"}`}
                    aria-hidden="true"
                    title={
                      statusLoading
                        ? "Checking RAG / Qdrant status…"
                        : ragStatus?.running
                          ? "RAG / Qdrant running"
                          : "RAG / Qdrant not running"
                    }
                  />
                ) : null}
                {hasError && (
                  <span className="coreui-sidebar__badge" aria-label="Error">
                    !
                  </span>
                )}
              </button>
            );
          })}
        </nav>
        {(onSettings || onStopWebUi) && (
          <div className="coreui-sidebar__dock">
            <footer className="coreui-sidebar__footer">
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
            </footer>
          </div>
        )}
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
