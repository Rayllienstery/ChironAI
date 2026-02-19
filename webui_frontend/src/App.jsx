import React, { useState, useEffect } from 'react';
import Tabs from './components/Tabs';
import ModelSettings from './components/ModelSettings';
import LogsTab from './components/LogsTab';
import SettingsTab from './components/SettingsTab';
import ModelTester from './components/ModelTester';
import RagTab from './components/RagTab';
import DebugLogPanel from './components/DebugLogPanel';
import { getSession } from './services/api';
import './styles/app.css';

function App() {
  const [activeTab, setActiveTab] = useState('model-settings');
  const [sessionId, setSessionId] = useState(null);
  const [debugLogOpen, setDebugLogOpen] = useState(false);

  useEffect(() => {
    // Initialize session
    getSession()
      .then((session) => {
        setSessionId(session.id);
      })
      .catch((error) => {
        console.error('Failed to initialize session:', error);
      });
  }, []);

  const tabs = [
    { id: 'model-settings', label: 'Model Settings' },
    { id: 'logs', label: 'Logs' },
    { id: 'settings', label: 'Settings' },
    { id: 'model-tester', label: 'Model Tester' },
    { id: 'rag', label: 'RAG / Qdrant' },
  ];

  const renderTabContent = () => {
    switch (activeTab) {
      case 'model-settings':
        return <ModelSettings sessionId={sessionId} />;
      case 'logs':
        return <LogsTab sessionId={sessionId} />;
      case 'settings':
        return <SettingsTab />;
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

