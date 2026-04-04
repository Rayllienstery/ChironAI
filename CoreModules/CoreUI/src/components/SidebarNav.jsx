import React, {
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";

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

function TabIcon({ tabId }) {
  const c = "coreui-sidebar__icon";
  const stroke = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.75,
    strokeLinecap: "round",
    strokeLinejoin: "round",
  };
  switch (tabId) {
    case "dashboard":
      return (
        <svg className={c} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
          <path d="M4 4h7v9H4zM13 4h7v5h-7zM13 11h7v9h-7zM4 15h7v5H4z" />
        </svg>
      );
    case "llm-proxy":
      return (
        <svg className={c} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
          <path d="M12 3a7 7 0 0 0-7 7v4H4v6h16v-6h-1v-4a7 7 0 0 0-7-7z" />
          <path d="M9 17v1M15 17v1" />
        </svg>
      );
    case "claw-proxy":
      return (
        <svg className={c} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
          <path d="M4 17l2-12h12l2 12" />
          <path d="M9 9h6M8 13h8" />
        </svg>
      );
    case "logs":
      return (
        <svg className={c} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
          <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
        </svg>
      );
    case "rag":
      return (
        <svg className={c} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
          <ellipse cx="12" cy="6" rx="8" ry="3" />
          <path d="M4 6v6c0 1.7 3.6 3 8 3s8-1.3 8-3V6" />
          <path d="M4 12v6c0 1.7 3.6 3 8 3s8-1.3 8-3v-6" />
        </svg>
      );
    case "crawler":
      return (
        <svg className={c} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
          <circle cx="12" cy="12" r="9" />
          <path d="M3 12h4M17 12h4M12 3v4M12 17v4" />
          <path d="M5.6 5.6l2.9 2.9M15.5 15.5l2.9 2.9M18.4 5.6l-2.9 2.9M8.5 15.5l-2.9 2.9" />
        </svg>
      );
    case "template-editor":
      return (
        <svg className={c} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
          <path d="M14 3l7 7-9 9H5v-7l9-9z" />
          <path d="M12 7l2 2" />
        </svg>
      );
    case "testing":
      return (
        <svg className={c} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
          <path d="M9 3h6v4H9zM6 8h12l-1 13H7L6 8z" />
          <path d="M10 14h4" />
        </svg>
      );
    default:
      return (
        <svg className={c} viewBox="0 0 24 24" aria-hidden="true" {...stroke}>
          <circle cx="12" cy="12" r="9" />
        </svg>
      );
  }
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
 * @param {{ tabs: { id: string, label: string }[], activeTab: string, onTabChange: (id: string) => void, tabErrors?: Record<string, boolean> }} props
 */
function SidebarNav({ tabs, activeTab, onTabChange, tabErrors }) {
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
