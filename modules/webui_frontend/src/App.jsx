import React, { useState, useEffect } from 'react';
import Tabs from './components/Tabs';
import DashboardTab from './components/DashboardTab';
import LogsTab from './components/LogsTab';
import SettingsTab from './components/SettingsTab';
import ModelTester from './components/ModelTester';
import RagTab from './components/RagTab';
import CrawlerTab from './components/CrawlerTab';
import TemplateEditorTab from './components/TemplateEditorTab';
import DebugLogPanel from './components/DebugLogPanel';
import {
  getSession,
  getSettings,
  getRagStatus,
  getOllamaStatus,
  getOpenWebUiStatus,
  getDashboardMetrics,
  startRag,
  stopRag,
  startOllama,
  stopOllama,
  startOpenWebUi,
  stopOpenWebUi,
  stopServer,
} from './services/api';
import Sparkline from './components/Sparkline';
import './styles/app.css';

const METRICS_HISTORY_LEN = 30;

function App() {
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sessionId, setSessionId] = useState(null);
  const [debugLogOpen, setDebugLogOpen] = useState(false);
  const [themeMode, setThemeMode] = useState('system');
  const [lightAccent, setLightAccent] = useState('purple');
  const [darkAccent, setDarkAccent] = useState('cyan');
  const [ollamaStatus, setOllamaStatus] = useState({ running: null, url: null });
  const [ragStatusInfo, setRagStatusInfo] = useState({ running: null, url: null });
  const [openWebUiStatus, setOpenWebUiStatus] = useState({ running: null, url: null });
  const [statusBusy, setStatusBusy] = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);
  const [dashboardMetrics, setDashboardMetrics] = useState(null);
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
        console.error('Failed to initialize session:', error);
      });
    
    // Load theme settings
    loadThemeSettings();
    
    // Listen for system theme changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleSystemThemeChange = () => {
      if (themeMode === 'system') {
        applyTheme('system', lightAccent, darkAccent);
      }
    };
    
    mediaQuery.addEventListener('change', handleSystemThemeChange);
    
    return () => {
      mediaQuery.removeEventListener('change', handleSystemThemeChange);
    };
  }, [themeMode, lightAccent, darkAccent]);

  useEffect(() => {
    // Load backend statuses on mount
    const loadStatuses = async () => {
      setStatusLoading(true);
      try {
        const [ollama, rag, openWebUi] = await Promise.all([
          getOllamaStatus().catch(() => ({ running: false })),
          getRagStatus().catch(() => ({ running: false })),
          getOpenWebUiStatus().catch(() => ({ running: false })),
        ]);
        setOllamaStatus(ollama);
        setRagStatusInfo(rag);
        setOpenWebUiStatus(openWebUi);
      } catch {
        // ignore
      } finally {
        setStatusLoading(false);
      }
    };
    loadStatuses();
  }, []);

  useEffect(() => {
    const poll = async () => {
      try {
        const m = await getDashboardMetrics();
        setDashboardMetrics(m);
        setMetricsHistory((prev) => {
          const next = { ...prev };
          if (m.gpu?.utilization_pct != null) {
            next.gpu_util = [...prev.gpu_util, m.gpu.utilization_pct].slice(-METRICS_HISTORY_LEN);
          }
          if (m.gpu?.memory_used_mb != null) {
            next.gpu_mem_used = [...prev.gpu_mem_used, m.gpu.memory_used_mb].slice(-METRICS_HISTORY_LEN);
          }
          if (m.gpu?.temperature_c != null) {
            next.gpu_temp = [...prev.gpu_temp, m.gpu.temperature_c].slice(-METRICS_HISTORY_LEN);
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

  const loadThemeSettings = async () => {
    try {
      const settings = await getSettings();
      const mode = settings.theme_mode || 'system';
      const light = settings.theme_light_accent || 'purple';
      const dark = settings.theme_dark_accent || 'cyan';
      setThemeMode(mode);
      setLightAccent(light);
      setDarkAccent(dark);
      applyTheme(mode, light, dark);
    } catch (error) {
      console.error('Failed to load theme settings:', error);
    }
  };

  const applyTheme = (mode, lightAccentColor, darkAccentColor) => {
    const root = document.documentElement;
    
    // Determine actual theme (system, light, or dark)
    let actualTheme = mode;
    if (mode === 'system') {
      actualTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
    
    // Apply theme class
    root.classList.remove('theme-light', 'theme-dark');
    root.classList.add(`theme-${actualTheme}`);
    
    // Apply accent color
    const accentColor = actualTheme === 'dark' ? darkAccentColor : lightAccentColor;
    root.setAttribute('data-accent-color', accentColor);
  };

  const handleThemeChange = (mode, lightAccentColor, darkAccentColor) => {
    setThemeMode(mode);
    setLightAccent(lightAccentColor);
    setDarkAccent(darkAccentColor);
    applyTheme(mode, lightAccentColor, darkAccentColor);
  };

  const tabs = [
    { id: 'dashboard', label: 'Dashboard' },
    { id: 'logs', label: 'Logs' },
    { id: 'model-tester', label: 'Model Tester' },
    { id: 'rag', label: 'RAG / Qdrant' },
    { id: 'crawler', label: 'Crawler / Indexer' },
    { id: 'template-editor', label: 'Template Editor' },
    { id: 'settings', label: 'Settings' },
  ];

  const renderTabContent = () => {
    switch (activeTab) {
      case 'dashboard':
        return <DashboardTab />;
      case 'logs':
        return <LogsTab sessionId={sessionId} />;
      case 'settings':
        return <SettingsTab 
          themeMode={themeMode}
          lightAccent={lightAccent}
          darkAccent={darkAccent}
          onThemeChange={handleThemeChange}
        />;
      case 'model-tester':
        return <ModelTester sessionId={sessionId} />;
      case 'rag':
        return <RagTab />;
      case 'crawler':
        return <CrawlerTab />;
      case 'template-editor':
        return <TemplateEditorTab />;
      default:
        return null;
    }
  };

  const handleOllamaStartStop = async (action) => {
    setStatusBusy(true);
    try {
      if (action === 'start') {
        await startOllama();
      } else {
        await stopOllama();
      }
      const status = await getOllamaStatus().catch(() => ({ running: false }));
      setOllamaStatus(status);
    } catch (e) {
      console.error('Failed to change Ollama status', e);
    } finally {
      setStatusBusy(false);
    }
  };

  const handleRagStartStop = async (action) => {
    setStatusBusy(true);
    try {
      if (action === 'start') {
        await startRag();
      } else {
        await stopRag();
      }
      const status = await getRagStatus().catch(() => ({ running: false }));
      setRagStatusInfo(status);
    } catch (e) {
      console.error('Failed to change RAG status', e);
    } finally {
      setStatusBusy(false);
    }
  };

  const handleServerStop = async () => {
    if (!window.confirm('Stop WebUI server? Current session will be closed.')) {
      return;
    }
    try {
      await stopServer();
      // Дадим серверу время корректно завершиться
      setTimeout(() => {
        // Попробуем закрыть вкладку (сработает, если окно было открыто скриптом)
        window.close();
      }, 300);
    } catch (e) {
      console.error('Failed to stop WebUI server', e);
    }
  };

  const openOllamaUI = () => {
    if (ollamaStatus?.url) {
      window.open(ollamaStatus.url, '_blank', 'noopener,noreferrer');
    }
  };

  const openRagUI = () => {
    if (ragStatusInfo?.url) {
      const base = ragStatusInfo.url.replace(/\/+$/, '');
      const url = `${base}/dashboard#/collections`;
      window.open(url, '_blank', 'noopener,noreferrer');
    }
  };

  const handleOpenWebUiStartStop = async (action) => {
    setStatusBusy(true);
    try {
      if (action === 'start') {
        await startOpenWebUi();
      } else {
        await stopOpenWebUi();
      }
      const status = await getOpenWebUiStatus().catch(() => ({ running: false }));
      setOpenWebUiStatus(status);
    } catch (e) {
      console.error('Failed to change Open WebUI status', e);
    } finally {
      setStatusBusy(false);
    }
  };

  const openOpenWebUiUI = () => {
    if (openWebUiStatus?.url) {
      window.open(openWebUiStatus.url, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <div className="app">
      <header className="app-header">
        <div className="app-header-row">
          <h1>TMRAG</h1>
          <div className="app-header-status">
          <div className="status-pill">
            <span className={`status-dot ${statusLoading ? 'updating' : (ollamaStatus.running ? 'running' : 'stopped')}`} />
            <span className="status-label">Ollama</span>
            {statusLoading ? (
              <span className="status-text status-text-updating">
                Updating status
                <span className="status-spinner" />
              </span>
            ) : (
              <span className="status-text">
                {ollamaStatus.running ? 'Running' : 'Stopped'}
              </span>
            )}
            <button
              type="button"
              className="status-button"
              disabled={statusBusy || statusLoading}
              onClick={() => handleOllamaStartStop(ollamaStatus.running ? 'stop' : 'start')}
            >
              {ollamaStatus.running ? 'Stop' : 'Start'}
            </button>
            {!statusLoading && ollamaStatus.running && ollamaStatus.url && (
              <button
                type="button"
                className="status-link-button"
                title="Open Ollama UI"
                onClick={openOllamaUI}
              >
                🔗
              </button>
            )}
          </div>
          <div className="status-pill">
            <span className={`status-dot ${statusLoading ? 'updating' : (ragStatusInfo.running ? 'running' : 'stopped')}`} />
            <span className="status-label">RAG / Qdrant</span>
            {statusLoading ? (
              <span className="status-text status-text-updating">
                Updating status
                <span className="status-spinner" />
              </span>
            ) : (
              <span className="status-text">
                {ragStatusInfo.running ? 'Running' : 'Stopped'}
              </span>
            )}
            <button
              type="button"
              className="status-button"
              disabled={statusBusy || statusLoading}
              onClick={() => handleRagStartStop(ragStatusInfo.running ? 'stop' : 'start')}
            >
              {ragStatusInfo.running ? 'Stop' : 'Start'}
            </button>
            {!statusLoading && ragStatusInfo.running && ragStatusInfo.url && (
              <button
                type="button"
                className="status-link-button"
                title="Open RAG / Qdrant UI"
                onClick={openRagUI}
              >
                🔗
              </button>
            )}
          </div>
          <div className="status-pill">
            <span className={`status-dot ${statusLoading ? 'updating' : (openWebUiStatus.running ? 'running' : 'stopped')}`} />
            <span className="status-label">Open WebUI</span>
            {statusLoading ? (
              <span className="status-text status-text-updating">
                Updating status
                <span className="status-spinner" />
              </span>
            ) : (
              <span className="status-text">
                {openWebUiStatus.running ? 'Running' : 'Stopped'}
              </span>
            )}
            <button
              type="button"
              className="status-button"
              disabled={statusBusy || statusLoading}
              onClick={() => handleOpenWebUiStartStop(openWebUiStatus.running ? 'stop' : 'start')}
            >
              {openWebUiStatus.running ? 'Stop' : 'Start'}
            </button>
            {!statusLoading && openWebUiStatus.running && openWebUiStatus.url && (
              <button
                type="button"
                className="status-link-button"
                title="Open Open WebUI"
                onClick={openOpenWebUiUI}
              >
                🔗
              </button>
            )}
          </div>
          <button
            type="button"
            className="server-stop-button"
            onClick={handleServerStop}
          >
            Stop WebUI
          </button>
        </div>
        </div>
{sessionId && (
          <div className="app-header-metrics">
            {dashboardMetrics?.gpu != null && (
              <>
                <div className="metric-card">
                  <span className="metric-label">GPU util</span>
                  <span className="metric-value">
                    {dashboardMetrics.gpu.utilization_pct != null ? `${dashboardMetrics.gpu.utilization_pct}%` : '—'}
                  </span>
                  <Sparkline data={metricsHistory.gpu_util} />
                </div>
                <div className="metric-card">
                  <span className="metric-label">GPU memory</span>
                  <span className="metric-value">
                    {dashboardMetrics.gpu.memory_used_mb != null && dashboardMetrics.gpu.memory_total_mb != null
                      ? `${(dashboardMetrics.gpu.memory_used_mb / 1024).toFixed(1)}/${(dashboardMetrics.gpu.memory_total_mb / 1024).toFixed(1)} GB`
                      : '—'}
                  </span>
                  <Sparkline data={metricsHistory.gpu_mem_used} />
                </div>
                <div className="metric-card">
                  <span className="metric-label">GPU temp</span>
                  <span className="metric-value">
                    {dashboardMetrics.gpu.temperature_c != null ? `${dashboardMetrics.gpu.temperature_c}°C` : '—'}
                  </span>
                  <Sparkline data={metricsHistory.gpu_temp} />
                </div>
              </>
            )}
            <div className="metric-card metric-card-combined">
              <span className="metric-segment">
                <span className="metric-label">Proxy</span>
                <span className="metric-value">{dashboardMetrics?.proxy_status ?? 'Idle'}</span>
              </span>
              <span className="metric-sep" aria-hidden="true">|</span>
              <span className="metric-segment">
                <span className="metric-label">LATEST REQUEST TOOK</span>
                <span className="metric-value">
                  {dashboardMetrics?.latest_request_seconds != null
                    ? `${Number(dashboardMetrics.latest_request_seconds).toFixed(1)} s`
                    : '—'}
                </span>
              </span>
              {dashboardMetrics?.latest_request_rag_steps != null && (
                <>
                  <span className="metric-sep" aria-hidden="true">|</span>
                  <span className="metric-segment">
                    <span className="metric-label">RAG steps</span>
                    <span className="metric-value">
                      embed {Number(dashboardMetrics.latest_request_rag_steps.embed_s ?? 0).toFixed(1)}s
                      {' | '}
                      search {Number(dashboardMetrics.latest_request_rag_steps.search_s ?? 0).toFixed(1)}s
                      {' | '}
                      rerank {Number(dashboardMetrics.latest_request_rag_steps.rerank_s ?? 0).toFixed(1)}s
                    </span>
                  </span>
                </>
              )}
              <span className="metric-sep" aria-hidden="true">|</span>
              <span className="metric-segment">
                <span className="metric-label">Total Tokens</span>
                <span className="metric-value">
                  {dashboardMetrics?.latest_request_total_tokens != null
                    ? String(dashboardMetrics.latest_request_total_tokens)
                    : '—'}
                </span>
              </span>
            </div>
          </div>
        )}
      </header>
      
      <Tabs tabs={tabs} activeTab={activeTab} onTabChange={setActiveTab} />
      
      <main className="app-main">
        {sessionId ? renderTabContent() : <div className="loading">Initializing session...</div>}
      </main>

      {sessionId && (
        <DebugLogPanel 
          open={debugLogOpen} 
          onToggle={() => setDebugLogOpen(!debugLogOpen)}
          sessionId={sessionId}
        />
      )}
    </div>
  );
}

export default App;

