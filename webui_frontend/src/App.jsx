import React, { useState, useEffect } from 'react';
import Tabs from './components/Tabs';
import LogsTab from './components/LogsTab';
import SettingsTab from './components/SettingsTab';
import ModelTester from './components/ModelTester';
import RagTab from './components/RagTab';
import DebugLogPanel from './components/DebugLogPanel';
import {
  getSession,
  getSettings,
  getRagStatus,
  getOllamaStatus,
  startRag,
  stopRag,
  startOllama,
  stopOllama,
  stopServer,
} from './services/api';
import './styles/app.css';

function App() {
  const [activeTab, setActiveTab] = useState('settings');
  const [sessionId, setSessionId] = useState(null);
  const [debugLogOpen, setDebugLogOpen] = useState(false);
  const [themeMode, setThemeMode] = useState('system');
  const [lightAccent, setLightAccent] = useState('purple');
  const [darkAccent, setDarkAccent] = useState('cyan');
  const [ollamaStatus, setOllamaStatus] = useState({ running: null, url: null });
  const [ragStatusInfo, setRagStatusInfo] = useState({ running: null, url: null });
  const [statusBusy, setStatusBusy] = useState(false);
  const [statusLoading, setStatusLoading] = useState(true);

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
        const [ollama, rag] = await Promise.all([
          getOllamaStatus().catch(() => ({ running: false })),
          getRagStatus().catch(() => ({ running: false })),
        ]);
        setOllamaStatus(ollama);
        setRagStatusInfo(rag);
      } catch {
        // ignore
      } finally {
        setStatusLoading(false);
      }
    };
    loadStatuses();
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
    { id: 'logs', label: 'Logs' },
    { id: 'model-tester', label: 'Model Tester' },
    { id: 'rag', label: 'RAG / Qdrant' },
    { id: 'settings', label: 'Settings' },
  ];

  const renderTabContent = () => {
    switch (activeTab) {
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

  return (
    <div className="app">
      <header className="app-header">
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
          <button
            type="button"
            className="server-stop-button"
            onClick={handleServerStop}
          >
            Stop WebUI
          </button>
        </div>
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

