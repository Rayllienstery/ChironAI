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

class TabErrorBoundary extends Component {
  state = { hasError: false, error: null };
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="app-main" style={{ padding: 24 }}>
          <h2>Something went wrong</h2>
          <pre style={{ whiteSpace: "pre-wrap", wordBreak: "break-word" }}>
            {this.state.error?.message ?? String(this.state.error)}
          </pre>
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
    msg.includes("dynamically imported")
  );
}

function lazyWithRetry(key, importer) {
  const storageKey = `coreui-lazy-retried:${String(key)}`;
  return lazy(() =>
    importer()
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
              window.location.reload();
              return new Promise(() => {});
            }
            window.sessionStorage.removeItem(storageKey);
          } catch {
            /* ignore */
          }
        }
        throw error;
      })
  );
}

const DashboardTab = lazyWithRetry("DashboardTab", () => import("./components/DashboardTab"));
const LogsTab = lazyWithRetry("LogsTab", () => import("./components/LogsTab"));
const SettingsTab = lazyWithRetry("SettingsTab", () => import("./components/SettingsTab"));
const LlmProxyTab = lazyWithRetry("LlmProxyTab", () => import("./components/LlmProxyTab"));
const LlmProxyBuildsTab = lazyWithRetry("LlmProxyBuildsTab", () => import("./components/LlmProxyBuildsTab"));
const RagTab = lazyWithRetry("RagTab", () => import("./components/RagTab"));
const CrawlerTab = lazyWithRetry("CrawlerTab", () => import("./components/CrawlerTab"));
const TestingTab = lazyWithRetry("TestingTab", () => import("./components/TestingTab"));
const TemplateEditorTab = lazyWithRetry("TemplateEditorTab", () => import("./components/TemplateEditorTab"));
const CoreUIShowcaseTab = lazyWithRetry("CoreUIShowcaseTab", () => import("./components/CoreUIShowcaseTab"));
const ExtensionsTab = lazyWithRetry("ExtensionsTab", () => import("./components/ExtensionsTab"));
const DevDocumentationTab = lazyWithRetry("DevDocumentationTab", () => import("./components/DevDocumentationTab"));
const ExtensionRuntimeTab = lazyWithRetry("ExtensionRuntimeTab", () => import("./components/ExtensionRuntimeTab"));
const DockerTab = lazyWithRetry("DockerTab", () => import("./components/DockerTab"));
const TokensSecurityTab = lazyWithRetry("TokensSecurityTab", () => import("./components/TokensSecurityTab"));

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
} from "./services/api";
import Sparkline from "./components/Sparkline";
import { NotificationCenterProvider } from "./components/NotificationCenterContext";
import NotificationCenterShell from "./components/NotificationCenterShell";
import RagTestRunNotificationBridge from "./components/RagTestRunNotificationBridge";
import ProxiesLiveNotificationBridge from "./components/ProxiesLiveNotificationBridge";
import OllamaPullNotificationBridge from "./components/OllamaPullNotificationBridge";
import InfrastructureAlertsBridge from "./components/InfrastructureAlertsBridge";
import WelcomeNotificationBridge from "./components/WelcomeNotificationBridge";
import ExtensionSecurityNotificationBridge from "./components/ExtensionSecurityNotificationBridge";
import "./styles/layout.css";
import "./styles/default-card.css";
import "./styles/sidebar.css";

const METRICS_HISTORY_LEN = 30;

function TabLoadingFallback() {
  return (
    <div style={{ padding: 24 }}>
      <Card className="loading" elevation="var(--md-sys-elevation-level1)">
        Loading tab…
      </Card>
    </div>
  );
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
  const [ragStatusInfo, setRagStatusInfo] = useState({
    running: null,
    url: null,
  });
  const [statusLoading, setStatusLoading] = useState(true);
  const [serviceStatusPollIntervalSec, setServiceStatusPollIntervalSec] = useState(5);
  const serviceStatusPollGenRef = useRef(0);
  const [dashboardMetrics, setDashboardMetrics] = useState(null);
  const [extensionTabs, setExtensionTabs] = useState([]);
  const [extensionServiceStatusByTabId, setExtensionServiceStatusByTabId] = useState({});
  const [metricsHistory, setMetricsHistory] = useState({
    gpu_util: [],
    gpu_mem_used: [],
    gpu_temp: [],
  });

  useEffect(() => {
    // Initialize session
    getSession()
      .then((session) => {
        setSessionId(session.id);
      })
      .catch((error) => {
        console.error("Failed to initialize session:", error);
      });

    // Load theme settings
    loadThemeSettings();

    // Listen for system theme changes
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    const handleSystemThemeChange = () => {
      if (themeMode === "system") {
        applyTheme("system", lightAccent, darkAccent);
      }
    };

    mediaQuery.addEventListener("change", handleSystemThemeChange);

    return () => {
      mediaQuery.removeEventListener("change", handleSystemThemeChange);
    };
  }, [themeMode, lightAccent, darkAccent]);

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
        void import("./components/ExtensionRuntimeTab");
      }
    } catch {
      setExtensionTabs([]);
      setExtensionServiceStatusByTabId({});
    }
  }, []);

  useEffect(() => {
    loadExtensionSurface();
  }, [loadExtensionSurface]);

  useEffect(() => {
    const gen = ++serviceStatusPollGenRef.current;
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
    loadStatuses(true);
    const ms = serviceStatusPollIntervalSec * 1000;
    const id = setInterval(() => loadStatuses(false), ms);
    return () => {
      clearInterval(id);
    };
  }, [serviceStatusPollIntervalSec, loadExtensionSurface]);

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
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

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
  };

  const handleThemeChange = (mode, lightAccentColor, darkAccentColor) => {
    setThemeMode(mode);
    setLightAccent(lightAccentColor);
    setDarkAccent(darkAccentColor);
    applyTheme(mode, lightAccentColor, darkAccentColor);
  };

  const tabs = [
    { id: "dashboard", label: "Dashboard", section: "Main" },
    { id: "docker", label: "Docker", section: "Main", iconUrl: DockerTabIcon },
    { id: "tokens-security", label: "Tokens and Security", section: "Main" },
    { id: "llm-proxy", label: "LLM Proxy", section: "Main" },
    { id: "rag-fusion-proxy", label: "RAG Fusion Proxy", section: "Main" },
    { id: "logs", label: "Logs", section: "Main" },
    { id: "template-editor", label: "Template Editor", section: "Main" },
    { id: "extensions", label: "Extensions", section: "Extensions" },
    ...extensionTabs.map((tab) => ({
      id: tab.id,
      label: tab.title || tab.id,
      icon: tab.icon || "",
      iconUrl: tab.icon_url || "",
      section: "Extensions",
    })),
    { id: "rag", label: "RAG / Qdrant", section: "RAG" },
    { id: "crawler", label: "Crawler / Indexer", section: "RAG" },
    { id: "testing", label: "Testing", section: "Developer Tools" },
    { id: "coreui-showcase", label: "CoreUI Showcase", section: "Developer Tools" },
    { id: "dev-documentation", label: "Dev Documentation", section: "Developer Tools" },
  ];

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
      case "extensions":
        return (
          <ExtensionsTab
            onErrorStateChange={(hasError) =>
              setTabErrors((prev) => ({ ...prev, extensions: hasError }))
            }
          />
        );
      case "dev-documentation":
        return <DevDocumentationTab />;
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
            onThemeChange={handleThemeChange}
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
          {sessionId ? (
            <TabErrorBoundary>
              <Suspense fallback={<TabLoadingFallback />}>
                {renderTabContent()}
              </Suspense>
            </TabErrorBoundary>
          ) : (
            <div className="loading">Initializing session...</div>
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
        <OllamaPullNotificationBridge
          onOpenOllama={() => {
            const ollamaTab = extensionTabs.find(
              (tab) => tab.id === "ollama" || tab.extension_id === "ollama-provider",
            );
            setActiveTab(ollamaTab?.id || "ollama");
          }}
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
