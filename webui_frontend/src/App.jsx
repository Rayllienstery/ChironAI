import React, { useState, useEffect } from 'react';
import Tabs from './components/Tabs';
import ModelSettings from './components/ModelSettings';
import LogsTab from './components/LogsTab';
import SettingsTab from './components/SettingsTab';
import ModelTester from './components/ModelTester';
import RagTab from './components/RagTab';
import DebugLogPanel from './components/DebugLogPanel';
import { getSession, getSettings } from './services/api';
import './styles/app.css';

function App() {
  const [activeTab, setActiveTab] = useState('model-settings');
  const [sessionId, setSessionId] = useState(null);
  const [debugLogOpen, setDebugLogOpen] = useState(false);
  const [themeMode, setThemeMode] = useState('system');
  const [lightAccent, setLightAccent] = useState('purple');
  const [darkAccent, setDarkAccent] = useState('cyan');

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
    { id: 'model-settings', label: 'Model Settings' },
    { id: 'logs', label: 'Logs' },
    { id: 'model-tester', label: 'Model Tester' },
    { id: 'rag', label: 'RAG / Qdrant' },
    { id: 'settings', label: 'Settings' },
  ];

  const renderTabContent = () => {
    switch (activeTab) {
      case 'model-settings':
        return <ModelSettings sessionId={sessionId} />;
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

  return (
    <div className="app">
      <header className="app-header">
        <h1>RAG Proxy WebUI</h1>
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

