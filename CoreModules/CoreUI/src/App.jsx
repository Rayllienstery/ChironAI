import {
  useState,
  useEffect,
  useRef,
  useCallback,
  Component,
  Suspense,
  lazy,
} from "react";
import SidebarNav from "./components/SidebarNav";
import ActionableError from "./components/ActionableError";
import CoreUIButton from "./components/CoreUIButton";
import { getLocale, t } from "./services/i18n";

class TabErrorBoundary extends Component {
  state = { hasError: false, error: null };
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="app-main" style={{ padding: 24 }}>
          <ActionableError
            error={this.state.error}
            title={t("common.error.boundary_title")}
            className="tab-error-boundary"
          />
          <p style={{ marginTop: 12, fontSize: "0.875rem" }}>{t("common.error.boundary_hint")}</p>
          <CoreUIButton
            variant="primary"
            type="button"
            onClick={() => window.location.reload()}
            style={{ marginTop: 8 }}
          >
            {t("common.error.reload")}
          </CoreUIButton>
        </div>
      );
    }
    return this.props.children;
  }
}

function isChunkLoadLikeError(error) {
  const msg = String(error?.message || "").toLowerCase();
  return (
    msg.includes("failed to fetch dynamically imported module") ||
    msg.includes("importing a module script failed") ||
    msg.includes("chunkloaderror") ||
    msg.includes("dynamically imported") ||
    msg.includes("dynamically importing")
  );
}

function lazyWithRetry(key, importer) {
  const storageKey = `coreui-lazy-retried:${String(key)}`;
  return lazy(() => {
    return loadTrackedModule(key, importer, { source: "navigation", timeoutMs: 20000 })
      .then((mod) => {
        try {
          window.sessionStorage.removeItem(storageKey);
        } catch {
          /* ignore */
        }
        return mod;
      })
      .catch((error) => {
        if (isChunkLoadLikeError(error)) {
          try {
            const alreadyRetried = window.sessionStorage.getItem(storageKey) === "1";
            if (!alreadyRetried) {
              window.sessionStorage.setItem(storageKey, "1");
              window.setTimeout(() => window.location.reload(), 50);
              return new Promise((_, reject) => {
                window.setTimeout(() => reject(error), 8000);
              });
            }
            window.sessionStorage.removeItem(storageKey);
          } catch {
            /* ignore */
          }
        }
        throw error;
      });
  });
}

const LAZY_MODULES = {
  LogsTab: () => import("./components/LogsTab"),
  DependenciesTab: () => import("./components/DependenciesTab"),
  SettingsTab: () => import("./components/SettingsTab"),
  LlmProxyTab: () => import("./components/LlmProxyTab"),
  LlmProxyBuildsTab: () => import("./components/LlmProxyBuildsTab"),
  RagTab: () => import("./components/RagTab"),
  CrawlerTab: () => import("./components/CrawlerTab"),
  TestingTab: () => import("./components/TestingTab"),
  TemplateEditorTab: () => import("./components/TemplateEditorTab"),
  CoreUIShowcaseTab: () => import("./components/CoreUIShowcaseTab"),
  ExtensionsTab: () => import("./components/ExtensionsTab"),
  DevDocumentationTab: () => import("./components/DevDocumentationTab"),
  SwaggerTab: () => import("./components/SwaggerTab"),
  ExtensionRuntimeTab: () => import("./components/ExtensionRuntimeTab"),
  DockerTab: () => import("./components/DockerTab"),
  TokensSecurityTab: () => import("./components/TokensSecurityTab"),
};

const TAB_MODULE_KEYS = {
  logs: "LogsTab",
  dependencies: "DependenciesTab",
  settings: "SettingsTab",
  "rag-fusion-proxy": "LlmProxyTab",
  "llm-proxy": "LlmProxyBuildsTab",
  rag: "RagTab",
  crawler: "CrawlerTab",
  testing: "TestingTab",
  "template-editor": "TemplateEditorTab",
  "coreui-showcase": "CoreUIShowcaseTab",
  extensions: "ExtensionsTab",
  "dev-documentation": "DevDocumentationTab",
  swagger: "SwaggerTab",
  docker: "DockerTab",
  "tokens-security": "TokensSecurityTab",
};

const IDLE_PREFETCH_TAB_IDS = [
  "logs",
  "llm-proxy",
  "rag-fusion-proxy",
  "rag",
  "crawler",
  "testing",
  "docker",
  "tokens-security",
  "extensions",
  "template-editor",
  "dependencies",
  "dev-documentation",
  "swagger",
  "coreui-showcase",
  "settings",
];

const IDLE_PREFETCH_EXTRA_MODULES = [
  { key: "ModelTester", importer: () => import("./components/ModelTester") },
  { key: "ProxyLogsAnalytics", importer: () => import("./components/ProxyLogsAnalytics") },
  { key: "RagTestsTab", importer: () => import("./components/RagTestsTab") },
  { key: "IndexerTester", importer: () => import("./components/IndexerTester") },
  { key: "RagTesterV2Tab", importer: () => import("./components/RagTesterV2Tab") },
  { key: "WebCallsTester", importer: () => import("./components/WebCallsTester") },
];

const LogsTab = lazyWithRetry("LogsTab", LAZY_MODULES.LogsTab);
const DependenciesTab = lazyWithRetry("DependenciesTab", LAZY_MODULES.DependenciesTab);
const SettingsTab = lazyWithRetry("SettingsTab", LAZY_MODULES.SettingsTab);
const LlmProxyTab = lazyWithRetry("LlmProxyTab", LAZY_MODULES.LlmProxyTab);
const LlmProxyBuildsTab = lazyWithRetry("LlmProxyBuildsTab", LAZY_MODULES.LlmProxyBuildsTab);
const RagTab = lazyWithRetry("RagTab", LAZY_MODULES.RagTab);
const CrawlerTab = lazyWithRetry("CrawlerTab", LAZY_MODULES.CrawlerTab);
const TestingTab = lazyWithRetry("TestingTab", LAZY_MODULES.TestingTab);
const TemplateEditorTab = lazyWithRetry("TemplateEditorTab", LAZY_MODULES.TemplateEditorTab);
const CoreUIShowcaseTab = lazyWithRetry("CoreUIShowcaseTab", LAZY_MODULES.CoreUIShowcaseTab);
const ExtensionsTab = lazyWithRetry("ExtensionsTab", LAZY_MODULES.ExtensionsTab);
const DevDocumentationTab = lazyWithRetry("DevDocumentationTab", LAZY_MODULES.DevDocumentationTab);
const SwaggerTab = lazyWithRetry("SwaggerTab", LAZY_MODULES.SwaggerTab);
const ExtensionRuntimeTab = lazyWithRetry("ExtensionRuntimeTab", LAZY_MODULES.ExtensionRuntimeTab);
const DockerTab = lazyWithRetry("DockerTab", LAZY_MODULES.DockerTab);
const TokensSecurityTab = lazyWithRetry("TokensSecurityTab", LAZY_MODULES.TokensSecurityTab);

import DockerTabIcon from "./assets/docker-mark.svg?url";
import Card from "./components/Card";
import {
  getSession,
  getSettings,
  getRagStatus,
  getExtensionTabs,
  getDashboardMetrics,
  stopServer,
  runRagTests,
  getRagTestRunStatus,
  cancelRagTestRun,
  postBrowserTiming,
  subscribeDockerEvents,
} from "./services/api";
import { loadTrackedModule } from "./services/moduleTimings";
import Sparkline from "./components/Sparkline";
import { NotificationCenterProvider } from "./components/NotificationCenterContext";
import NotificationCenterShell from "./components/NotificationCenterShell";
import RagTestRunNotificationBridge from "./components/RagTestRunNotificationBridge";
import ProxiesLiveNotificationBridge from "./components/ProxiesLiveNotificationBridge";
import InfrastructureAlertsBridge from "./components/InfrastructureAlertsBridge";
import WelcomeNotificationBridge from "./components/WelcomeNotificationBridge";
import ExtensionSecurityNotificationBridge from "./components/ExtensionSecurityNotificationBridge";
import DashboardTab from "./components/DashboardTab";
import PerformanceTab from "./components/PerformanceTab";
import "./styles/layout.css";
import "./styles/default-card.css";
import "./styles/sidebar.css";
import StandByScreen from "./components/StandByScreen";
import "./styles/components/StandByScreen.css";

const METRICS_HISTORY_LEN = 30;
const SHELL_REQUEST_BOOT_DELAY_MS = 800;
const PERFORMANCE_SHELL_REQUEST_DELAY_MS = 1500;

function scheduleIdleWork(callback, timeout = 3000) {
  if (typeof window === "undefined") return null;
  if (typeof window.requestIdleCallback === "function") {
    return { type: "idle", id: window.requestIdleCallback(callback, { timeout }) };
  }
  return { type: "timeout", id: window.setTimeout(callback, 1) };
}

function cancelIdleWork(handle) {
  if (!handle || typeof window === "undefined") return;
  if (handle.type === "idle" && typeof window.cancelIdleCallback === "function") {
    window.cancelIdleCallback(handle.id);
    return;
  }
  window.clearTimeout(handle.id);
}

function AppLoadingState({ moduleName }) {
  return (
    <StandByScreen
      moduleName={moduleName}
      icon="progress_activity"
      size="md"
    />
  );
}

function TabLoadingFallback({ moduleName }) {
  return <AppLoadingState moduleName={moduleName} />;
}

function clampServiceStatusPollSec(raw) {
  const n = parseInt(String(raw ?? ""), 10);
  if (Number.isNaN(n)) return 5;
  return Math.min(300, Math.max(2, n));
}

function isTransientFetchLikeError(message) {
  const lower = String(message || "").toLowerCase();
  return (
    lower.includes("failed to fetch") ||
    lower.includes("networkerror") ||
    lower.includes("load failed") ||
    lower.includes("failed to get run status") ||
    lower.includes("typeerror: failed to fetch")
  );
}

function App() {
  const [activeTab, setActiveTab] = useState("dashboard");
  const [scrollToRagModelsSection, setScrollToRagModelsSection] =
    useState(false);
  const [testingSubTab, setTestingSubTab] = useState("model-tester");
  const [sessionId, setSessionId] = useState(null);
  const [sessionError, setSessionError] = useState(false);
  const [ragTestRunJobId, setRagTestRunJobId] = useState(null);
  const [ragTestRunning, setRagTestRunning] = useState(false);
  const [ragTestRunProgress, setRagTestRunProgress] = useState(null);
  const [ragTestRunResults, setRagTestRunResults] = useState([]);
  const [ragTestRunError, setRagTestRunError] = useState(null);
  const [pendingRagRunOpenId, setPendingRagRunOpenId] = useState(null);
  const ragTestStatusPollFailuresRef = useRef(0);
  const [llmProxyBuildsFocusSubTab, setLlmProxyBuildsFocusSubTab] = useState(null);
  const [logsFocusSubTab, setLogsFocusSubTab] = useState(null);
  const [tabErrors, setTabErrors] = useState({});
  const [tabActivity, setTabActivity] = useState({});
  const [themeMode, setThemeMode] = useState("system");
  const [lightAccent, setLightAccent] = useState("purple");
  const [darkAccent, setDarkAccent] = useState("cyan");
  const [locale, setLocaleState] = useState(getLocale());
  const [ragStatusInfo, setRagStatusInfo] = useState({
    running: null,
    url: null,
  });
  const [statusLoading, setStatusLoading] = useState(true);
  const [serviceStatusPollIntervalSec, setServiceStatusPollIntervalSec] = useState(5);
  const serviceStatusPollGenRef = useRef(0);
  const reactMountOffsetMsRef = useRef(null);
  const browserTimingPostedRef = useRef(false);
  const [dashboardMetrics, setDashboardMetrics] = useState(null);
  const [extensionTabs, setExtensionTabs] = useState([]);
  const [extensionServiceStatusByTabId, setExtensionServiceStatusByTabId] = useState({});
  const [metricsHistory, setMetricsHistory] = useState({
    gpu_util: [],
    gpu_mem_used: [],
    gpu_temp: [],
  });
  const shellRequestDelayMs =
    activeTab === "performance"
      ? PERFORMANCE_SHELL_REQUEST_DELAY_MS
      : SHELL_REQUEST_BOOT_DELAY_MS;

  const prefetchTabModule = useCallback((tabId, source = "intent") => {
    const key = TAB_MODULE_KEYS[String(tabId || "")];
    const importer = key ? LAZY_MODULES[key] : null;
    if (!key || typeof importer !== "function") return Promise.resolve(null);
    return loadTrackedModule(key, importer, {
      source,
      timeoutMs: 0,
      staleAfterMs: 12000,
    }).catch(() => null);
  }, []);

  const initSession = useCallback(() => {
    setSessionError(false);
    let cancelled = false;

    (async () => {
      const maxAttempts = 45;
      for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
        if (cancelled) return;
        try {
          const session = await getSession({
            maxRetries: 1,
            timeoutMs: 3000,
            baseDelayMs: 0,
          });
          if (cancelled) return;
          setSessionId(session.id);
          setSessionError(false);
          return;
        } catch (error) {
          if (cancelled) return;
          if (attempt >= maxAttempts - 1) {
            console.error("Failed to initialize session after retries:", error);
            setSessionError(true);
            return;
          }
          const delayMs = Math.min(3000, 400 + attempt * 150);
          await new Promise((resolve) => window.setTimeout(resolve, delayMs));
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (reactMountOffsetMsRef.current == null) {
      reactMountOffsetMsRef.current =
        typeof performance !== "undefined" && typeof performance.now === "function"
          ? performance.now()
          : null;
    }

    // Remove the stand-by loader now that React has rendered
    try {
      document.getElementById('app-loader')?.remove();
    } catch {
      // ignore
    }

    let cancelSessionInit = null;
    const shellRequestTimer = window.setTimeout(() => {
      try {
        const nav = window?.performance?.timing;
        if (!browserTimingPostedRef.current && nav && nav.navigationStart) {
          const now = Date.now();
          const reactMountMs =
            reactMountOffsetMsRef.current != null
              ? Math.max(0, Math.round(reactMountOffsetMsRef.current))
              : Math.max(0, now - nav.navigationStart);
          browserTimingPostedRef.current = true;
          postBrowserTiming({
            navigationStart: nav.navigationStart,
            fetchStart: nav.fetchStart,
            responseStart: nav.responseStart,
            responseEnd: nav.responseEnd,
            domInteractive: nav.domInteractive,
            domContentLoadedEventStart: nav.domContentLoadedEventStart,
            domContentLoadedEventEnd: nav.domContentLoadedEventEnd,
            domComplete: nav.domComplete,
            loadEventStart: nav.loadEventStart,
            loadEventEnd: nav.loadEventEnd,
            reactMountMs,
            reportedAt: now,
          }).catch(() => {});
        }
      } catch {
        // Non-critical
      }
      cancelSessionInit = initSession();
      loadThemeSettings();
    }, shellRequestDelayMs);

    // Listen for system theme changes
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleSystemThemeChange = () => {
      if (themeMode === "system") {
        applyTheme("system", lightAccent, darkAccent);
      }
    };

    mediaQuery.addEventListener("change", handleSystemThemeChange);

    return () => {
      window.clearTimeout(shellRequestTimer);
      cancelSessionInit?.();
      mediaQuery.removeEventListener("change", handleSystemThemeChange);
    };
  }, [themeMode, lightAccent, darkAccent, shellRequestDelayMs, initSession]);

  const loadExtensionSurface = useCallback(async () => {
    try {
      const [tabsData] = await Promise.all([
        getExtensionTabs().catch(() => ({ tabs: [] })),
      ]);
      const tabs = Array.isArray(tabsData?.tabs) ? tabsData.tabs : [];
      const serviceStatusByTabId = {};
      tabs.forEach((tab) => {
        if (!tab?.status) return;
        serviceStatusByTabId[tab.id] = {
          running: Boolean(tab.status.running),
          title: tab.title || tab.id,
          tone: tab.status.tone || "",
          message: tab.status.message || "",
        };
      });
      setExtensionTabs(tabs);
      setExtensionServiceStatusByTabId(serviceStatusByTabId);
      if (tabs.length > 0) {
        void loadTrackedModule("ExtensionRuntimeTab", LAZY_MODULES.ExtensionRuntimeTab, {
          source: "extension surface",
        }).catch(() => null);
      }
    } catch {
      setExtensionTabs([]);
      setExtensionServiceStatusByTabId({});
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      loadExtensionSurface();
    }, shellRequestDelayMs);
    return () => window.clearTimeout(timer);
  }, [loadExtensionSurface, shellRequestDelayMs]);

  useEffect(() => {
    let cancelled = false;
    let timerId = null;
    let idleHandle = null;
    let index = 0;
    const queue = [
      ...IDLE_PREFETCH_TAB_IDS.map((tabId) => ({ tabId })),
      ...IDLE_PREFETCH_EXTRA_MODULES,
    ];

    const prefetchNext = () => {
      if (cancelled || index >= queue.length) return;
      const item = queue[index];
      index += 1;
      idleHandle = scheduleIdleWork(() => {
        idleHandle = null;
        const promise = item.tabId
          ? prefetchTabModule(item.tabId, "idle prefetch")
          : loadTrackedModule(item.key, item.importer, {
              source: "idle prefetch",
              timeoutMs: 0,
              staleAfterMs: 12000,
            }).catch(() => null);
        promise.finally(() => {
          if (!cancelled) prefetchNext();
        });
      }, 4000);
    };

    timerId = window.setTimeout(prefetchNext, shellRequestDelayMs + 700);

    return () => {
      cancelled = true;
      if (timerId != null) window.clearTimeout(timerId);
      cancelIdleWork(idleHandle);
    };
  }, [prefetchTabModule, shellRequestDelayMs]);

  useEffect(() => {
    const gen = ++serviceStatusPollGenRef.current;
    let refreshTimer = null;
    const loadStatuses = async (isInitial) => {
      if (isInitial) setStatusLoading(true);
      try {
        const [rag] = await Promise.all([
          getRagStatus().catch(() => ({ running: false })),
        ]);
        if (serviceStatusPollGenRef.current !== gen) return;
        setRagStatusInfo(rag);
        loadExtensionSurface().catch(() => {});
      } catch {
        // ignore
      } finally {
        if (isInitial && serviceStatusPollGenRef.current === gen) {
          setStatusLoading(false);
        }
      }
    };
    const scheduleRefresh = (event = {}) => {
      if (event?.ok === false) return;
      if (serviceStatusPollGenRef.current !== gen) return;
      if (refreshTimer != null) window.clearTimeout(refreshTimer);
      refreshTimer = window.setTimeout(() => {
        refreshTimer = null;
        loadStatuses(false);
      }, 300);
    };
    const firstTimer = window.setTimeout(() => {
      loadStatuses(true);
    }, shellRequestDelayMs);
    const fallbackMs = Math.max(60, Number(serviceStatusPollIntervalSec) || 60) * 1000;
    const source = subscribeDockerEvents(scheduleRefresh, () => {});
    const id = setInterval(() => loadStatuses(false), fallbackMs);
    return () => {
      window.clearTimeout(firstTimer);
      if (refreshTimer != null) window.clearTimeout(refreshTimer);
      source?.close?.();
      clearInterval(id);
    };
  }, [serviceStatusPollIntervalSec, loadExtensionSurface, shellRequestDelayMs]);

  useEffect(() => {
    const poll = async () => {
      try {
        const m = await getDashboardMetrics();
        setDashboardMetrics(m);
        setMetricsHistory((prev) => {
          const next = { ...prev };
          if (m.gpu?.utilization_pct != null) {
            next.gpu_util = [...prev.gpu_util, m.gpu.utilization_pct].slice(
              -METRICS_HISTORY_LEN,
            );
          }
          if (m.gpu?.memory_used_mb != null) {
            next.gpu_mem_used = [
              ...prev.gpu_mem_used,
              m.gpu.memory_used_mb,
            ].slice(-METRICS_HISTORY_LEN);
          }
          if (m.gpu?.temperature_c != null) {
            next.gpu_temp = [...prev.gpu_temp, m.gpu.temperature_c].slice(
              -METRICS_HISTORY_LEN,
            );
          }
          return next;
        });
      } catch {
        // ignore
      }
    };
    const firstTimer = window.setTimeout(poll, shellRequestDelayMs);
    const id = setInterval(poll, 5000);
    return () => {
      window.clearTimeout(firstTimer);
      clearInterval(id);
    };
  }, [shellRequestDelayMs]);

  const openCompletedRagRunModal = useCallback((runId) => {
    const rid = String(runId || "").trim();
    if (!rid) return;
    setActiveTab("testing");
    setTestingSubTab("rag-tests");
    setPendingRagRunOpenId(rid);
  }, []);

  useEffect(() => {
    if (!ragTestRunJobId || !ragTestRunning) return;
    let cancelled = false;
    let t;

    const poll = async () => {
      let nextDelayMs = 500;
      try {
        const data = await getRagTestRunStatus(ragTestRunJobId);
        ragTestStatusPollFailuresRef.current = 0;
        setRagTestRunProgress(data.progress || null);
        if (data.results && data.results.length > 0) {
          setRagTestRunResults(data.results);
        }
        if (data.status === "completed" || data.status === "cancelled") {
          const completedId = String(data?.job_id || ragTestRunJobId || "").trim();
          setRagTestRunResults(data.results || []);
          setRagTestRunJobId(null);
          setRagTestRunProgress(null);
          setRagTestRunning(false);
          if (data.error) setRagTestRunError(data.error);
          if (data.status === "completed" && completedId) {
            openCompletedRagRunModal(completedId);
          }
          return;
        }
      } catch (e) {
        const msg = String(e?.message || "");
        const lower = msg.toLowerCase();
        const isTransient = isTransientFetchLikeError(msg);
        const isNotFound = lower.includes("job not found");

        ragTestStatusPollFailuresRef.current += 1;
        const failures = ragTestStatusPollFailuresRef.current;

        if (isNotFound && failures >= 12) {
          setRagTestRunError(
            "Run status is no longer available in memory. Open Run history for final result."
          );
          setRagTestRunJobId(null);
          setRagTestRunProgress(null);
          setRagTestRunning(false);
          return;
        }

        // Keep run state alive on polling errors (including unknown ones); only
        // repeated "job not found" is treated as terminal.
        nextDelayMs = Math.min(3000, 500 * Math.max(1, failures));
        console.warn(
          isTransient
            ? "RAG test status polling transient error:"
            : "RAG test status polling non-fatal error:",
          msg || e
        );
      }
      if (!cancelled) {
        t = setTimeout(poll, nextDelayMs);
      }
    };
    t = setTimeout(poll, 300);
    return () => {
      cancelled = true;
      clearTimeout(t);
    };
  }, [ragTestRunJobId, ragTestRunning, openCompletedRagRunModal]);

  const handlePendingRagRunOpenHandled = useCallback(() => {
    setPendingRagRunOpenId(null);
  }, []);

  const handleRagTestRunStart = async (body) => {
    setRagTestRunError(null);
    setRagTestRunResults([]);
    ragTestStatusPollFailuresRef.current = 0;
    try {
      const data = await runRagTests(body);
      if (data.job_id) {
        setRagTestRunJobId(data.job_id);
        setRagTestRunning(true);
        setRagTestRunProgress({
          current_index: 0,
          total: 0,
          current_test_name: "",
          passed: 0,
          failed: 0,
          pending: 0,
        });
        return;
      }
      setRagTestRunResults(data.results || []);
    } catch (e) {
      setRagTestRunError(e.message);
    }
  };

  const handleRagTestRunCancel = async () => {
    if (!ragTestRunJobId) return;
    try {
      await cancelRagTestRun(ragTestRunJobId);
    } catch (e) {
      setRagTestRunError(e.message);
    }
  };

  const handleOpenLlmProxyTrace = useCallback(() => {
    setActiveTab("logs");
    setLogsFocusSubTab("traces");
  }, []);

  const handleOpenLlmProxyAutocomplete = useCallback(() => {
    setActiveTab("llm-proxy");
    setLlmProxyBuildsFocusSubTab("autocomplete");
  }, []);

  const handleOpenLlmProxySecurity = useCallback(() => {
    setActiveTab("tokens-security");
  }, []);

  const consumeLlmProxyBuildsFocusSubTab = useCallback(() => {
    setLlmProxyBuildsFocusSubTab(null);
  }, []);

  const consumeLogsFocusSubTab = useCallback(() => {
    setLogsFocusSubTab(null);
  }, []);

  const loadThemeSettings = async () => {
    try {
      const settings = await getSettings();
      const mode = settings.theme_mode || "system";
      const light = settings.theme_light_accent || "purple";
      const dark = settings.theme_dark_accent || "cyan";
      setThemeMode(mode);
      setLightAccent(light);
      setDarkAccent(dark);
      applyTheme(mode, light, dark);
      setServiceStatusPollIntervalSec(
        clampServiceStatusPollSec(settings.service_status_poll_interval_sec),
      );
    } catch (error) {
      console.error("Failed to load theme settings:", error);
    }
  };

  const applyTheme = (mode, lightAccentColor, darkAccentColor) => {
    const root = document.documentElement;

    // Determine actual theme (system, light, or dark)
    let actualTheme = mode;
    if (mode === "system") {
      actualTheme = window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
    }

    // Apply theme class
    root.classList.remove("theme-light", "theme-dark");
    root.classList.add(`theme-${actualTheme}`);

    // Apply accent color
    const accentColor =
      actualTheme === "dark" ? darkAccentColor : lightAccentColor;
    root.setAttribute("data-accent-color", accentColor);

    // Persist for instant restoration on next page load (prevents purple flash).
    try {
      localStorage.setItem(
        "chironai_theme",
        JSON.stringify({ mode, lightAccent: lightAccentColor, darkAccent: darkAccentColor }),
      );
    } catch {
      // safe: localStorage may be unavailable (private mode / quota)
    }
  };

  const handleThemeChange = (mode, lightAccentColor, darkAccentColor) => {
    setThemeMode(mode);
    setLightAccent(lightAccentColor);
    setDarkAccent(darkAccentColor);
    applyTheme(mode, lightAccentColor, darkAccentColor);
  };

  const tabs = [
    { id: "dashboard", label: t("nav.dashboard"), section: "Main" },
    { id: "docker", label: t("nav.docker"), section: "Main", iconUrl: DockerTabIcon },
    { id: "tokens-security", label: t("nav.tokens_security"), section: "Main" },
    { id: "logs", label: t("nav.logs"), section: "Main" },
    { id: "dependencies", label: t("nav.dependencies"), section: "Main" },
    { id: "llm-proxy", label: t("nav.llm_proxy"), section: "Core Functionality" },
    { id: "rag-fusion-proxy", label: t("nav.rag_fusion_proxy"), section: "Core Functionality" },
    { id: "template-editor", label: t("nav.template_editor"), section: "Core Functionality" },
    { id: "rag", label: t("nav.rag"), section: "RAG" },
    { id: "crawler", label: t("nav.crawler"), section: "RAG" },
    { id: "extensions", label: t("nav.extensions"), section: "Extensions" },
    ...extensionTabs.map((tab) => ({
      id: tab.id,
      label: tab.title || tab.id,
      icon: tab.icon || "",
      iconUrl: tab.icon_url || "",
      section: "Extensions",
    })),
    { id: "testing", label: t("nav.testing"), section: "Developer Tools" },
    { id: "coreui-showcase", label: t("nav.coreui_showcase"), section: "Developer Tools" },
    { id: "dev-documentation", label: t("nav.dev_documentation"), section: "Developer Tools" },
    { id: "swagger", label: t("nav.swagger"), section: "Developer Tools" },
    { id: "performance", label: t("nav.performance"), section: "Developer Tools" },
  ];
  const activeTabLabel = tabs.find((tab) => tab.id === activeTab)?.label || activeTab;

  const renderTabContent = () => {
    const activeExtensionTab = extensionTabs.find((tab) => tab.id === activeTab);
    if (activeExtensionTab) {
      return (
        <ExtensionRuntimeTab
          extensionId={activeExtensionTab.extension_id}
          title={activeExtensionTab.title}
          onErrorStateChange={(state) => {
            const loading = state === "loading";
            setTabActivity((prev) => ({ ...prev, [activeExtensionTab.id]: loading }));
            setTabErrors((prev) => ({ ...prev, [activeExtensionTab.id]: loading ? false : Boolean(state) }));
          }}
        />
      );
    }
    switch (activeTab) {
      case "dashboard":
        return (
          <DashboardTab
            onNavigate={setActiveTab}
            onOpenLogs={() => setActiveTab("logs")}
            onOpenLlmProxyAutocomplete={handleOpenLlmProxyAutocomplete}
            onOpenLlmProxySecurity={handleOpenLlmProxySecurity}
          />
        );
      case "logs":
        return <LogsTab sessionId={sessionId} focusSubTab={logsFocusSubTab} onFocusSubTabConsumed={consumeLogsFocusSubTab} />;
      case "dependencies":
        return <DependenciesTab />;
      case "extensions":
        return (
          <ExtensionsTab
            onErrorStateChange={(hasError) =>
              setTabErrors((prev) => ({ ...prev, extensions: hasError }))
            }
            onExtensionSurfaceChange={loadExtensionSurface}
          />
        );
      case "dev-documentation":
        return <DevDocumentationTab />;
      case "performance":
        return <PerformanceTab />;
      case "swagger":
        return <SwaggerTab />;
      case "testing":
        return (
          <TestingTab
            sessionId={sessionId}
            activeSubTab={testingSubTab}
            onSubTabChange={setTestingSubTab}
            runJobId={ragTestRunJobId}
            running={ragTestRunning}
            runProgress={ragTestRunProgress}
            results={ragTestRunResults}
            runError={ragTestRunError}
            pendingOpenRunId={pendingRagRunOpenId}
            onPendingOpenHandled={handlePendingRagRunOpenHandled}
            onStartRun={handleRagTestRunStart}
            onCancelRun={handleRagTestRunCancel}
          />
        );
      case "docker":
        return <DockerTab />;
      case "tokens-security":
        return <TokensSecurityTab />;
      case "rag":
        return (
          <RagTab
            scrollToModelsSection={scrollToRagModelsSection}
            onModelsSectionScrolled={() => setScrollToRagModelsSection(false)}
          />
        );
      case "crawler":
        return <CrawlerTab />;
      case "rag-fusion-proxy":
        return (
          <LlmProxyTab
            onOpenLogs={() => setActiveTab("logs")}
          />
        );
      case "llm-proxy":
        return (
          <LlmProxyBuildsTab
            focusSubTab={llmProxyBuildsFocusSubTab}
            onFocusSubTabConsumed={consumeLlmProxyBuildsFocusSubTab}
          />
        );
      case "template-editor":
        return <TemplateEditorTab />;
      case "coreui-showcase":
        return <CoreUIShowcaseTab />;
      case "settings":
        return (
          <SettingsTab
            themeMode={themeMode}
            lightAccent={lightAccent}
            darkAccent={darkAccent}
            locale={locale}
            onThemeChange={handleThemeChange}
            onLocaleChange={setLocaleState}
            onAppSettingsSaved={(saved) =>
              setServiceStatusPollIntervalSec(
                clampServiceStatusPollSec(saved.service_status_poll_interval_sec),
              )
            }
          />
        );
      default:
        return null;
    }
  };

  const handleServerStop = async () => {
    if (!window.confirm("Stop WebUI server? Current session will be closed.")) {
      return;
    }
    try {
      await stopServer();
      // Give the server time to shut down properly.
      setTimeout(() => {
        // Try to close the tab (works if the window was opened by script).
        window.close();
      }, 300);
    } catch (e) {
      console.error("Failed to stop WebUI server", e);
    }
  };

  return (
    <NotificationCenterProvider sessionId={sessionId}>
    <div className="app">
      <SidebarNav
        tabs={tabs}
        activeTab={activeTab}
        onTabChange={setActiveTab}
        onPrefetchTab={(tabId) => prefetchTabModule(tabId, "intent")}
        tabErrors={tabErrors}
        tabActivity={tabActivity}
        onSettings={() => setActiveTab("settings")}
        onStopWebUi={handleServerStop}
        settingsActive={activeTab === "settings"}
        ragStatus={ragStatusInfo}
        serviceStatusByTabId={extensionServiceStatusByTabId}
        statusLoading={statusLoading}
      />
      <div className="app-main-column">
        <header className="app-header">
          {sessionId && (
            <div className="app-header-metrics">
            {dashboardMetrics?.gpu != null && (
              <>
                <Card className="metric-card">
                  <span className="metric-label">GPU util</span>
                  <span className="metric-value">
                    {dashboardMetrics.gpu.utilization_pct != null
                      ? `${dashboardMetrics.gpu.utilization_pct}%`
                      : "—"}
                  </span>
                  <Sparkline data={metricsHistory.gpu_util} />
                </Card>
                <Card className="metric-card">
                  <span className="metric-label">GPU memory</span>
                  <span className="metric-value">
                    {dashboardMetrics.gpu.memory_used_mb != null &&
                    dashboardMetrics.gpu.memory_total_mb != null
                      ? `${(dashboardMetrics.gpu.memory_used_mb / 1024).toFixed(1)}/${(dashboardMetrics.gpu.memory_total_mb / 1024).toFixed(1)} GB`
                      : "—"}
                  </span>
                  <Sparkline data={metricsHistory.gpu_mem_used} />
                </Card>
                <Card className="metric-card">
                  <span className="metric-label">GPU temp</span>
                  <span className="metric-value">
                    {dashboardMetrics.gpu.temperature_c != null
                      ? `${dashboardMetrics.gpu.temperature_c}°C`
                      : "—"}
                  </span>
                  <Sparkline data={metricsHistory.gpu_temp} />
                </Card>
              </>
            )}

          </div>
          )}
        </header>

        <main className="app-main">
          <TabErrorBoundary>
            <Suspense fallback={<TabLoadingFallback moduleName={activeTabLabel} />}>
              {renderTabContent()}
            </Suspense>
          </TabErrorBoundary>
          {sessionError && !sessionId && (
            <div className="session-error session-error--inline">
              <p>Backend session is unavailable. Tabs will work once the server finishes starting — click Retry or wait a moment.</p>
              <button className="session-retry-btn" onClick={initSession}>
                Retry
              </button>
            </div>
          )}
        </main>
      </div>

      {sessionId && (
        <RagTestRunNotificationBridge
          ragTestRunning={ragTestRunning}
          ragTestRunJobId={ragTestRunJobId}
          ragTestRunProgress={ragTestRunProgress}
          ragTestRunError={ragTestRunError}
          onCancel={handleRagTestRunCancel}
          onGoToRagTests={() => {
            setActiveTab("testing");
            setTestingSubTab("rag-tests");
          }}
        />
      )}
      {sessionId && (
        <ProxiesLiveNotificationBridge
          onOpenLlmProxyTrace={handleOpenLlmProxyTrace}
        />
      )}
      {sessionId && (
        <InfrastructureAlertsBridge pollIntervalSec={serviceStatusPollIntervalSec} />
      )}
      {sessionId && <ExtensionSecurityNotificationBridge />}
      {sessionId && <WelcomeNotificationBridge />}
      {sessionId && <NotificationCenterShell onOpenRagRunDetails={openCompletedRagRunModal} />}
      </div>
    </NotificationCenterProvider>
  );
}

export default App;
